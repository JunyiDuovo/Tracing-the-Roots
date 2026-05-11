(function () {
  function buildPartialFetchUrl(href) {
    var u = new URL(href, window.location.origin);
    u.searchParams.set("partial", "1");
    return u.pathname + u.search;
  }

  document.addEventListener(
    "click",
    function (ev) {
      var link = ev.target.closest("a.js-members-expand-load");
      if (!link) {
        return;
      }
      var wrap = document.getElementById("members-expand-container");
      if (!wrap || !wrap.contains(link)) {
        return;
      }
      var href = link.getAttribute("href");
      if (!href) {
        return;
      }
      ev.preventDefault();
      var y = window.scrollY || document.documentElement.scrollTop;

      fetch(buildPartialFetchUrl(href), {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      })
        .then(function (res) {
          if (!res.ok) {
            throw new Error("http");
          }
          return res.json();
        })
        .then(function (data) {
          if (data.error) {
            throw new Error(String(data.error));
          }
          var tb = document.getElementById("members-table-body");
          var ex = document.getElementById("members-expand-container");
          if (tb) {
            tb.innerHTML = data.tbody_html || "";
          }
          if (ex) {
            ex.innerHTML = data.expand_html || "";
          }
          if (data.history_url) {
            try {
              history.replaceState(null, "", data.history_url);
            } catch (_e) {
              /* ignore */
            }
          }
          requestAnimationFrame(function () {
            requestAnimationFrame(function () {
              window.scrollTo(0, y);
            });
          });
        })
        .catch(function () {
          window.location.href = href;
        });
    },
    false
  );
})();
