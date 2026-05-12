(function () {
  function svgEyeOpen() {
    return (
      '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24" aria-hidden="true">' +
      '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>' +
      '<circle cx="12" cy="12" r="3"/>' +
      "</svg>"
    );
  }

  function svgEyeOff() {
    return (
      '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24" aria-hidden="true">' +
      '<path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/>' +
      '<path d="M1 1l22 22"/>' +
      "</svg>"
    );
  }

  document.querySelectorAll(".js-password-field").forEach(function (wrap) {
    if (wrap.querySelector(".password-toggle")) return;
    var input = wrap.querySelector("input");
    if (!input) return;

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "password-toggle";
    btn.innerHTML =
      '<span class="password-toggle-icons">' +
      '<span class="password-toggle-icon password-toggle-icon--hide">' +
      svgEyeOff() +
      "</span>" +
      '<span class="password-toggle-icon password-toggle-icon--show" hidden>' +
      svgEyeOpen() +
      "</span>" +
      "</span>";

    function sync() {
      var revealed = input.type === "text";
      btn.classList.toggle("is-revealed", revealed);
      btn.setAttribute("aria-pressed", revealed ? "true" : "false");
      btn.setAttribute("aria-label", revealed ? "隐藏密码" : "显示密码");
      var ih = btn.querySelector(".password-toggle-icon--hide");
      var sh = btn.querySelector(".password-toggle-icon--show");
      if (ih) ih.hidden = revealed;
      if (sh) sh.hidden = !revealed;
    }

    btn.addEventListener("mousedown", function (e) {
      e.preventDefault();
    });
    btn.addEventListener("click", function () {
      input.type = input.type === "password" ? "text" : "password";
      sync();
    });

    sync();
    wrap.appendChild(btn);
  });
})();
