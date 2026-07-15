(function () {
  // Local fleet: static site on :8080, Streamlit dispatch on :8502.
  // Always use absolute dispatch URLs on localhost so links never 404 as /app/.
  const host = window.location.hostname;
  const isLocal = host === "127.0.0.1" || host === "localhost";
  let appUrl = (document.body.dataset.appUrl || "http://127.0.0.1:8502/").replace(/\/?$/, "/");

  if (isLocal) {
    appUrl = `http://${host}:8502/`;
  } else if (appUrl.indexOf("/app") === -1 && window.location.port !== "8502") {
    // production-style path when not on Streamlit port
    appUrl = appUrl.replace(/\/?$/, "/") ;
  }

  const driverUrl = appUrl.includes("view=driver")
    ? appUrl
    : appUrl + (appUrl.indexOf("?") >= 0 ? "&" : "?") + "view=driver";

  document.body.dataset.appUrl = appUrl;
  document.body.dataset.driverUrl = driverUrl;

  document.querySelectorAll("[data-app-link]").forEach((el) => {
    el.setAttribute("href", appUrl);
    el.setAttribute("target", "_blank");
    el.setAttribute("rel", "noopener");
  });

  document.querySelectorAll("[data-driver-link]").forEach((el) => {
    el.setAttribute("href", driverUrl);
    el.setAttribute("target", "_blank");
    el.setAttribute("rel", "noopener");
  });

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/sw.js", { scope: "/" }).catch(() => {});
  }

  let deferredDispatchPrompt;
  let deferredDriverPrompt;

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    const path = window.location.pathname || "";
    if (path.includes("driver")) {
      deferredDriverPrompt = e;
      const driverBtn = document.getElementById("install-driver-pwa");
      if (driverBtn) driverBtn.hidden = false;
    } else {
      deferredDispatchPrompt = e;
      const installBtn = document.getElementById("install-pwa");
      if (installBtn) installBtn.hidden = false;
    }
  });

  const installBtn = document.getElementById("install-pwa");
  if (installBtn) {
    installBtn.addEventListener("click", async () => {
      if (!deferredDispatchPrompt) return;
      deferredDispatchPrompt.prompt();
      await deferredDispatchPrompt.userChoice;
      deferredDispatchPrompt = null;
      installBtn.hidden = true;
    });
  }

  const driverBtn = document.getElementById("install-driver-pwa");
  if (driverBtn) {
    driverBtn.addEventListener("click", async () => {
      if (!deferredDriverPrompt) {
        window.location.href = driverUrl;
        return;
      }
      deferredDriverPrompt.prompt();
      await deferredDriverPrompt.userChoice;
      deferredDriverPrompt = null;
      driverBtn.hidden = true;
    });
  }
})();