/* Dashboard behaviour. Every page works without it; this only adds convenience:
   - confirm dialog for forms marked data-confirm
   - selects marked data-autosubmit submit their filter form on change
   - order page: courier/tracking fields appear when "Shipped" is chosen
   - discount form: show only the value field that matches the chosen kind */
(function () {
  "use strict";

  /* ---- Confirm dialog (capture phase so ui.js's window.confirm fallback never runs) ---- */
  var dialog = document.getElementById("confirm-dialog");
  document.addEventListener("submit", function (e) {
    var form = e.target;
    var message = form.getAttribute && form.getAttribute("data-confirm");
    if (!message || !dialog || typeof dialog.showModal !== "function") return; // fall back to ui.js
    e.preventDefault();
    e.stopPropagation();
    var submitter = e.submitter;
    dialog.querySelector("#confirm-message").textContent = message;
    var accept = dialog.querySelector("#confirm-accept");
    accept.textContent = (submitter && submitter.textContent.trim()) || "Confirm";
    var done = function () { accept.removeEventListener("click", onAccept); dialog.removeEventListener("close", onClose); };
    var onAccept = function () {
      done();
      dialog.close();
      form.removeAttribute("data-confirm");
      if (form.requestSubmit) form.requestSubmit(submitter || undefined); else form.submit();
    };
    var onClose = function () { done(); };
    accept.addEventListener("click", onAccept);
    dialog.addEventListener("close", onClose);
    dialog.showModal();
  }, true);

  document.addEventListener("click", function (e) {
    if (dialog && e.target.closest && e.target.closest("[data-dialog-close]")) dialog.close();
  });

  /* ---- Auto-submit filters ---- */
  document.addEventListener("change", function (e) {
    var el = e.target;
    if (el.matches && el.matches("select[data-autosubmit]") && el.form) el.form.submit();
  });

  /* ---- Ship fields ---- */
  function syncShip(form) {
    var select = form.querySelector("select[name='status']");
    var box = form.querySelector("[data-ship-fields]");
    if (select && box) box.hidden = select.value !== "shipped";
  }
  document.querySelectorAll("form[data-ship-form]").forEach(function (form) {
    syncShip(form);
    form.addEventListener("change", function () { syncShip(form); });
  });

  /* ---- Discount kind ---- */
  var codeForm = document.querySelector("form[data-code-form]");
  if (codeForm) {
    var kind = codeForm.querySelector("[name='kind']");
    var pct = codeForm.querySelector("[data-kind-percentage]");
    var fixed = codeForm.querySelector("[data-kind-fixed]");
    var sync = function () { if (pct) pct.hidden = kind.value !== "percentage"; if (fixed) fixed.hidden = kind.value !== "fixed"; };
    if (kind) { sync(); kind.addEventListener("change", sync); }
  }
})();
