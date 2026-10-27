// Kept in a separate file because the Content-Security-Policy blocks inline JS.
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("form.confirm-delete").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm("Delete this part and its history?")) {
        e.preventDefault();
      }
    });
  });
});
