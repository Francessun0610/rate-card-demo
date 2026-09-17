/* =====================================================================
   FEEDBACK  -  submission transport
   ---------------------------------------------------------------------
   Everything between "the reviewer pressed Submit" and "the destination
   confirmed the write". No user interface lives here.

   This portfolio build ships with no endpoint configured, so every
   function below returns early and no request is ever constructed. The
   notes that follow describe the shape of the transport for a private
   build that does configure one.

   The prototype is a static site and the destination is a cross origin
   Web App, so a readable JSON POST is not available: the destination
   answers no CORS preflight and returns no Access-Control-Allow-Origin.
   The submission therefore goes out as a single no-cors POST with a CORS
   safe content type, which the browser will send but whose response it
   will not let us read.

   An opaque response proves only that the browser dispatched the
   request. It is never treated as success. Confirmation is a separate,
   read only JSONP call that asks the Web App whether one specific
   submission id was written, and the Web App only answers yes after
   saveAndClose() has returned. That is the only thing allowed to move
   the interface to a success state.

   Exactly one POST per attempt. A retry reuses the same submission id so
   the Web App's duplicate protection can drop it, which means an
   uncertain retry can never produce a second entry in the document.
   ===================================================================== */
(function () {
  "use strict";

  var CONFIG = window.RCF_FEEDBACK_CONFIG;
  var SCHEMA_VERSION = 1;

  /* Apps Script echoes this back as the JSONP function name, so it is
   * validated on both sides. Anything that is not a plain identifier is
   * rejected rather than escaped. */
  var CALLBACK_PATTERN = /^[A-Za-z_$][A-Za-z0-9_$]*$/;
  var callbackSeq = 0;

  /* One confirmation loop at a time. A second Submit press while the
   * first is still confirming must not start a competing poller. */
  var activeConfirmation = null;

  /* ------------------------------------------------------------ helpers */

  function wait(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  function clip(value, max) {
    if (value == null) return null;
    var text = String(value);
    return text.length > max ? text.slice(0, max) : text;
  }

  function newSubmissionId() {
    try {
      if (window.crypto && typeof window.crypto.randomUUID === "function") {
        return window.crypto.randomUUID();
      }
    } catch (err) { /* fall through */ }
    return "rcf-" + Date.now().toString(36) + "-" +
      Math.random().toString(36).slice(2, 10);
  }

  function blobToDataUrl(blob) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () { resolve(String(reader.result || "")); };
      reader.onerror = function () {
        reject(new Error("The screenshot could not be read."));
      };
      reader.readAsDataURL(blob);
    });
  }

  function loadImage(src) {
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () { resolve(img); };
      img.onerror = function () {
        reject(new Error("The screenshot could not be decoded."));
      };
      img.src = src;
    });
  }

  /* Bytes actually represented by a base64 data URL, without decoding it. */
  function decodedBytes(dataUrl) {
    var comma = dataUrl.indexOf(",");
    if (comma === -1) return 0;
    var body = dataUrl.length - comma - 1;
    var padding = dataUrl.endsWith("==") ? 2 : dataUrl.endsWith("=") ? 1 : 0;
    return Math.max(0, Math.floor(body * 3 / 4) - padding);
  }

  /* -------------------------------------------------- screenshot sizing
     The input is already the flattened export: the capture with the
     reviewer's arrows and rectangles drawn into it. Every step below
     rescales that same composite, so the annotations shrink with the
     image and can never be dropped or drawn at the wrong place. Aspect
     ratio is preserved at every step, so the image is never distorted. */

  var PNG_SCALES = [0.85, 0.7, 0.6, 0.5, 0.4];
  var JPEG_STEPS = [
    { scale: 1, quality: 0.92 },
    { scale: 1, quality: 0.85 },
    { scale: 0.85, quality: 0.82 },
    { scale: 0.7, quality: 0.8 },
    { scale: 0.6, quality: 0.75 }
  ];

  function drawScaled(img, scale, mime, quality) {
    var width = Math.max(1, Math.round(img.naturalWidth * scale));
    var height = Math.max(1, Math.round(img.naturalHeight * scale));
    var canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    var ctx = canvas.getContext("2d");
    /* A screenshot is mostly text, so the smoothing quality is what keeps
     * labels legible after a downscale. */
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    if (mime === "image/jpeg") {
      /* JPEG has no alpha. Without this the transparent regions of a PNG
       * composite render black. */
      ctx.fillStyle = "#FFFFFF";
      ctx.fillRect(0, 0, width, height);
    }
    ctx.drawImage(img, 0, 0, width, height);
    return {
      dataUrl: canvas.toDataURL(mime, quality),
      width: width,
      height: height
    };
  }

  function fits(dataUrl) {
    return decodedBytes(dataUrl) <= CONFIG.TARGET_SCREENSHOT_BYTES &&
      dataUrl.length <= CONFIG.MAX_SCREENSHOT_BYTES;
  }

  /**
   * Turn the annotated export blob into a data URL the Web App will
   * accept. Never throws.
   *
   * @returns {Promise<object>} { ok, dataUrl, format, bytes, width,
   *          height, downscaled, reason }
   */
  async function prepareScreenshot(blob) {
    if (!blob || typeof blob.size !== "number" || blob.size === 0) {
      return { ok: true, dataUrl: null, format: null, bytes: 0, reason: "no-screenshot" };
    }

    var original;
    try {
      original = await blobToDataUrl(blob);
    } catch (err) {
      return { ok: false, dataUrl: null, reason: "The screenshot could not be read." };
    }

    if (fits(original)) {
      return {
        ok: true,
        dataUrl: original,
        format: "png",
        bytes: decodedBytes(original),
        downscaled: false
      };
    }

    var objectUrl = URL.createObjectURL(blob);
    try {
      var img = await loadImage(objectUrl);
      var i;

      for (i = 0; i < PNG_SCALES.length; i++) {
        var png = drawScaled(img, PNG_SCALES[i], "image/png");
        if (fits(png.dataUrl)) {
          return {
            ok: true,
            dataUrl: png.dataUrl,
            format: "png",
            bytes: decodedBytes(png.dataUrl),
            width: png.width,
            height: png.height,
            downscaled: true
          };
        }
      }

      /* PNG could not get there without shrinking the text past legible.
       * A high quality JPEG holds detail far better at this size. */
      for (i = 0; i < JPEG_STEPS.length; i++) {
        var step = JPEG_STEPS[i];
        var jpeg = drawScaled(img, step.scale, "image/jpeg", step.quality);
        if (fits(jpeg.dataUrl)) {
          return {
            ok: true,
            dataUrl: jpeg.dataUrl,
            format: "jpeg",
            bytes: decodedBytes(jpeg.dataUrl),
            width: jpeg.width,
            height: jpeg.height,
            downscaled: step.scale !== 1
          };
        }
      }

      return {
        ok: false,
        dataUrl: null,
        reason:
          "The screenshot is too large to attach, even after resizing. " +
          "Capture a smaller window and try again."
      };
    } catch (err) {
      return {
        ok: false,
        dataUrl: null,
        reason: (err && err.message) || "The screenshot could not be prepared."
      };
    } finally {
      URL.revokeObjectURL(objectUrl);
    }
  }

  /* ------------------------------------------------------------ payload */

  /**
   * One flat JSON object. Only what the document entry needs: no
   * filesystem paths, no credentials, no identity beyond what the Web App
   * already knows from the Disney session it authenticated.
   */
  function buildPayload(input) {
    var source = input.source || {};
    var now = input.now || new Date();
    var viewport = {
      width: window.innerWidth || null,
      height: window.innerHeight || null,
      devicePixelRatio: window.devicePixelRatio || null
    };

    var timestampLocal;
    try {
      timestampLocal = now.toLocaleString(undefined, {
        year: "numeric", month: "short", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
        timeZoneName: "short"
      });
    } catch (err) {
      timestampLocal = now.toString();
    }

    return {
      schemaVersion: SCHEMA_VERSION,
      submissionId: input.submissionId,
      feedback: clip((input.feedback || "").trim(), CONFIG.MAX_FEEDBACK_CHARS) || null,
      pageName: clip(source.title || document.title, CONFIG.MAX_FIELD_CHARS),
      view: clip(source.viewLabel, CONFIG.MAX_FIELD_CHARS),
      viewState: clip(source.stateLabel, CONFIG.MAX_FIELD_CHARS),
      version: clip(
        (document.body && document.body.getAttribute("data-version")) || null,
        CONFIG.MAX_FIELD_CHARS
      ),
      route: clip(
        source.route || (document.body && document.body.getAttribute("data-route")) || null,
        CONFIG.MAX_FIELD_CHARS
      ),
      section: clip(input.section, CONFIG.MAX_FIELD_CHARS),
      mode: clip(
        (document.body && document.body.getAttribute("data-mode")) || null,
        CONFIG.MAX_FIELD_CHARS
      ),
      url: clip(window.location.href, CONFIG.MAX_FIELD_CHARS),
      timestampIso: now.toISOString(),
      timestampLocal: clip(timestampLocal, CONFIG.MAX_FIELD_CHARS),
      viewport: viewport,
      screenshotDataUrl: input.screenshotDataUrl || null,
      screenshotFormat: input.screenshotFormat || null,
      screenshotBytes: input.screenshotBytes || 0
    };
  }

  /* ---------------------------------------------------------- dispatch */

  /**
   * The single POST. no-cors because the destination answers no
   * preflight, text/plain because that is the only JSON friendly content
   * type a no-cors request may set, and credentials included so the
   * reviewer's session travels with it.
   *
   * Resolving means the browser sent it. Nothing more. Unreachable in the
   * offline portfolio build: isConfigured is false.
   */
  async function dispatch(payload) {
    if (!CONFIG.isConfigured) {
      return { dispatched: false, reason: CONFIG.configurationProblem };
    }

    /* The response is opaque, so waiting on it buys nothing except the
     * ability to notice a hard network failure. A slow append must not
     * hold the interface on "Submitting" indefinitely, so the wait is
     * capped and confirmation takes over from there. */
    var controller = new AbortController();
    var timer = setTimeout(function () {
      controller.abort();
    }, CONFIG.DISPATCH_TIMEOUT_MS);

    try {
      await fetch(CONFIG.GOOGLE_FEEDBACK_WEB_APP_URL, {
        method: "POST",
        mode: "no-cors",
        credentials: "include",
        cache: "no-store",
        redirect: "follow",
        headers: { "Content-Type": "text/plain;charset=UTF-8" },
        body: JSON.stringify(payload),
        signal: controller.signal
      });
      return { dispatched: true, awaited: true, reason: null };
    } catch (err) {
      /* Abort means we stopped waiting, not that the request failed. The
       * body was already on the wire, so this is still one dispatch and it
       * must not be retried: confirmation will settle it either way. */
      if (err && err.name === "AbortError") {
        return { dispatched: true, awaited: false, reason: "slow-response" };
      }
      return {
        dispatched: false,
        awaited: false,
        reason: (err && err.message) || "The request could not be sent."
      };
    } finally {
      clearTimeout(timer);
    }
  }

  /* ------------------------------------------------------------- JSONP
     Read only, and only ever for the two non-sensitive answers the Web
     App is allowed to give: a health ping and whether one submission id
     has been written. The callback name is generated here, validated
     here, and validated again on the server. */

  function jsonp(params, timeoutMs) {
    return new Promise(function (resolve) {
      var name = "__rcfCb" + (++callbackSeq) + "_" +
        Math.random().toString(36).slice(2, 10);

      if (!CALLBACK_PATTERN.test(name)) {
        resolve({ answered: false, reason: "bad-callback" });
        return;
      }

      var script = document.createElement("script");
      var settled = false;
      var timer = 0;

      function finish(result) {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        try { delete window[name]; } catch (err) { window[name] = undefined; }
        if (script.parentNode) script.parentNode.removeChild(script);
        resolve(result);
      }

      window[name] = function (data) { finish({ answered: true, data: data }); };

      script.onerror = function () {
        finish({ answered: false, reason: "unreachable" });
      };
      script.onload = function () {
        /* The script fetched but our callback never ran. That is what a
         * sign in redirect looks like from here: an HTML page served
         * where JavaScript was expected. */
        setTimeout(function () {
          finish({ answered: false, reason: "no-callback" });
        }, 0);
      };

      timer = setTimeout(function () {
        finish({ answered: false, reason: "timeout" });
      }, timeoutMs);

      var query = Object.keys(params)
        .map(function (key) {
          return encodeURIComponent(key) + "=" + encodeURIComponent(params[key]);
        })
        .concat("prefix=" + encodeURIComponent(name))
        .join("&");

      script.async = true;
      script.src = CONFIG.GOOGLE_FEEDBACK_WEB_APP_URL + "?" + query;
      document.head.appendChild(script);
    });
  }

  /**
   * Is there a usable session for this deployment?
   *
   * A health ping that comes back means the browser reached the Web App
   * as an authenticated user. Anything else means it did not, and by far
   * the most common cause is not being signed in. Third party cookie
   * restrictions can produce the same symptom, which is why the message
   * the interface shows offers sign in rather than asserting it.
   */
  async function probeAuth() {
    if (!CONFIG.isConfigured) {
      return { authenticated: false, reason: CONFIG.configurationProblem };
    }
    var result = await jsonp({ health: "1" }, CONFIG.AUTH_PROBE_TIMEOUT_MS);
    if (result.answered && result.data && result.data.ok) {
      return { authenticated: true, reason: null };
    }
    return { authenticated: false, reason: result.reason || "no-answer" };
  }

  /**
   * Poll until the Web App reports the document write finished.
   *
   * Never posts anything. Never resends. Stops the moment received is
   * true, and gives up after the schedule is exhausted so a spinner can
   * never run forever.
   */
  async function confirm(submissionId, onAttempt) {
    if (activeConfirmation) {
      return { received: false, reason: "already-confirming", attempts: 0 };
    }
    var token = { cancelled: false };
    activeConfirmation = token;

    var everAnswered = false;
    var schedule = CONFIG.CONFIRM_SCHEDULE_MS;

    try {
      for (var i = 0; i < schedule.length; i++) {
        await wait(schedule[i]);
        if (token.cancelled) {
          return { received: false, reason: "cancelled", attempts: i, everAnswered: everAnswered };
        }

        if (typeof onAttempt === "function") onAttempt(i + 1, schedule.length);

        var result = await jsonp(
          { submissionId: submissionId },
          CONFIG.CONFIRM_REQUEST_TIMEOUT_MS
        );
        if (token.cancelled) {
          return { received: false, reason: "cancelled", attempts: i + 1, everAnswered: everAnswered };
        }
        if (result.answered) {
          everAnswered = true;
          if (result.data && result.data.received === true) {
            return { received: true, attempts: i + 1, everAnswered: true };
          }
        }
      }
      return {
        received: false,
        reason: everAnswered ? "not-written-in-time" : "no-answer",
        attempts: schedule.length,
        everAnswered: everAnswered
      };
    } finally {
      if (activeConfirmation === token) activeConfirmation = null;
    }
  }

  function cancelConfirm() {
    if (activeConfirmation) activeConfirmation.cancelled = true;
  }

  window.RCFFeedbackTransport = Object.freeze({
    newSubmissionId: newSubmissionId,
    prepareScreenshot: prepareScreenshot,
    buildPayload: buildPayload,
    dispatch: dispatch,
    probeAuth: probeAuth,
    confirm: confirm,
    cancelConfirm: cancelConfirm
  });
})();
