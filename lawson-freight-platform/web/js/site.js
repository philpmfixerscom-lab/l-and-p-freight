(function () {
  let appUrl = (document.body.dataset.appUrl || "/app/").replace(/\/?$/, "/");
  const host = window.location.hostname;
  if ((host === "127.0.0.1" || host === "localhost") && window.location.port !== "8502") {
    appUrl = `http://${host}:8502/`;
  }
  const driverUrl = appUrl + "?view=driver";

  document.body.dataset.appUrl = appUrl;
  document.body.dataset.driverUrl = driverUrl;

  document.querySelectorAll("[data-app-link]").forEach((el) => {
    el.setAttribute("href", appUrl);
  });

  document.querySelectorAll("[data-driver-link]").forEach((el) => {
    el.setAttribute("href", driverUrl);
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