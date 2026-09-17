/* =====================================================================
   FEEDBACK  -  runtime configuration
   ---------------------------------------------------------------------
   Portfolio build. This copy of the prototype runs offline: there is no
   submission endpoint and no destination document, so nothing is sent
   anywhere when a reviewer presses Submit.

   The capture, annotation, and draft interface is unchanged. The panel
   reads isConfigured from here, reports demo mode, and keeps the local
   fallbacks (Copy feedback, Download screenshot) as the way a note
   leaves the browser.

   To point a private build at a real destination, set WEB_APP_URL to a
   deployment URL and keep it out of any public repository.
   ===================================================================== */
(function () {
  "use strict";

  /* Empty on purpose. Every network path in feedback-transport.js is
   * gated on isConfigured below, so an empty endpoint means no request
   * is ever constructed. */
  var WEB_APP_URL = "";
  var DOCUMENT_ID = "";

  var OFFLINE_REASON =
    "This portfolio build runs offline, so feedback is not sent anywhere.";

  /* Retained so a private build can validate its own endpoint before a
   * reviewer discovers the problem mid submission. */
  function validateWebAppUrl(raw) {
    if (!raw || typeof raw !== "string") {
      return { valid: false, reason: OFFLINE_REASON };
    }
    var parsed;
    try {
      parsed = new URL(raw);
    } catch (err) {
      return { valid: false, reason: "The endpoint is not a valid URL." };
    }
    if (parsed.protocol !== "https:") {
      return { valid: false, reason: "The endpoint must use HTTPS." };
    }
    return { valid: true, reason: null };
  }

  /* Enough to identify a deployment in a log line, never enough to
   * reproduce it. */
  function redactUrl(raw) {
    if (!raw || typeof raw !== "string") return "(not configured)";
    try {
      var parsed = new URL(raw);
      var trimmed = parsed.pathname.replace(
        /\/s\/([^/]{0,8})[^/]*\//,
        "/s/$1\u2026/"
      );
      return parsed.origin + trimmed;
    } catch (err) {
      return "(unparseable endpoint)";
    }
  }

  var validation = validateWebAppUrl(WEB_APP_URL);

  window.RCF_FEEDBACK_CONFIG = Object.freeze({
    GOOGLE_FEEDBACK_WEB_APP_URL: WEB_APP_URL,
    GOOGLE_FEEDBACK_DOCUMENT_ID: DOCUMENT_ID,

    /* Unchanged client-side limits. The editor still enforces them so the
     * capture and draft experience behaves the same in demo mode. */
    MAX_SCREENSHOT_BYTES: 4 * 1024 * 1024,
    TARGET_SCREENSHOT_BYTES: Math.round(2.8 * 1024 * 1024),

    MAX_FEEDBACK_CHARS: 300,
    MAX_FIELD_CHARS: 500,

    CONFIRM_SCHEDULE_MS: Object.freeze([700, 1000, 1500, 2000, 3000, 4000, 5000]),
    CONFIRM_REQUEST_TIMEOUT_MS: 8000,
    AUTH_PROBE_TIMEOUT_MS: 6000,
    DISPATCH_TIMEOUT_MS: 15000,

    isConfigured: validation.valid,
    configurationProblem: validation.reason,
    validateWebAppUrl: validateWebAppUrl,
    redactUrl: redactUrl
  });
})();
