(function () {
  var backBtn = document.querySelector(".js-back-nav");
  if (!backBtn) return;

  var backUrl = backBtn.getAttribute("data-back-url");
  if (!backUrl) return;

  var modal = document.getElementById("leave-unsaved-modal");
  var pendingUrl = null;

  document.querySelectorAll("form[data-track-dirty]").forEach(function (form) {
    form.addEventListener("input", function () {
      form.setAttribute("data-dirty-modified", "1");
    });
    form.addEventListener("change", function () {
      form.setAttribute("data-dirty-modified", "1");
    });
    form.addEventListener("submit", function () {
      form.removeAttribute("data-dirty-modified");
    });
  });

  function hasDirtyForm() {
    return document.querySelector("form[data-track-dirty][data-dirty-modified]");
  }

  function openModal(url) {
    pendingUrl = url;
    if (!modal) {
      window.location.href = url;
      return;
    }
    modal.hidden = false;
    modal.removeAttribute("aria-hidden");
  }

  function closeModal() {
    if (!modal) return;
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    pendingUrl = null;
  }

  /** 注册等页：用 fetch 读 302 Location 再跳转，避免程序化 submit 不触发整页导航。 */
  function submitFormThenLeave(form, fallbackUrl) {
    var action = form.getAttribute("action") || window.location.pathname;
    var method = (form.getAttribute("method") || "GET").toUpperCase();
    var fd = new FormData(form);
    fetch(action, {
      method: method,
      body: fd,
      credentials: "same-origin",
      redirect: "manual",
    })
      .then(function (response) {
        var st = response.status;
        if (st === 302 || st === 301 || st === 303 || st === 307 || st === 308) {
          var loc = response.headers.get("Location");
          if (loc) {
            window.location.href = new URL(loc, window.location.href).href;
            return;
          }
          window.location.href = fallbackUrl;
          return;
        }
        if (st === 0) {
          window.location.href = fallbackUrl;
          return;
        }
        if (response.ok && st === 200) {
          return response.text().then(function (html) {
            document.open();
            document.write(html);
            document.close();
          });
        }
        window.location.reload();
      })
      .catch(function () {
        window.location.href = fallbackUrl;
      });
  }

  /** 先校验再提交；失败时不关闭弹窗。成功则整页跳转，无需手动关弹窗。 */
  function submitTrackedForm() {
    var form = document.querySelector("form[data-track-dirty][data-dirty-modified]");
    if (!form) return false;
    if (typeof form.reportValidity === "function" && !form.reportValidity()) {
      return false;
    }
    var leaveFallback = form.getAttribute("data-leave-after-submit");
    if (leaveFallback) {
      submitFormThenLeave(form, leaveFallback);
      return true;
    }
    var primary = form.querySelector(
      'button[type="submit"]:not([name="_delete"])'
    );
    if (typeof form.requestSubmit === "function") {
      try {
        if (primary) {
          form.requestSubmit(primary);
        } else {
          form.requestSubmit();
        }
        return true;
      } catch (e) {
        /* 校验失败时 requestSubmit 会抛错 */
      }
    }
    if (primary) {
      primary.click();
    } else {
      form.submit();
    }
    return true;
  }

  backBtn.addEventListener("click", function () {
    if (hasDirtyForm()) {
      openModal(backUrl);
    } else {
      window.location.href = backUrl;
    }
  });

  var saveBtn = document.getElementById("leave-btn-save");
  var discardBtn = document.getElementById("leave-btn-discard");
  var cancelBtn = document.getElementById("leave-btn-cancel");
  var xBtn = document.getElementById("leave-unsaved-x");

  if (saveBtn) {
    saveBtn.addEventListener("click", function () {
      submitTrackedForm();
    });
  }
  if (discardBtn) {
    discardBtn.addEventListener("click", function () {
      var u = pendingUrl || backUrl;
      closeModal();
      window.location.href = u;
    });
  }
  if (cancelBtn) cancelBtn.addEventListener("click", closeModal);
  if (xBtn) xBtn.addEventListener("click", closeModal);

  document.addEventListener("keydown", function (e) {
    if (modal && !modal.hidden && e.key === "Escape") closeModal();
  });
})();
