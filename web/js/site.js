(function () {
  const appUrl = document.body.dataset.appUrl || "/app/";
  document.body.dataset.appUrl = appUrl;

  document.querySelectorAll("[data-app-link]").forEach((el) => {
    el.setAttribute("href", appUrl);
  });

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/sw.js", { scope: "/" }).catch(() => {});
  }

  let deferredPrompt;
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt = e;
    const installBtn = document.getElementById("install-pwa");
    if (installBtn) installBtn.hidden = false;
  });

  const installBtn = document.getElementById("install-pwa");
  if (installBtn) {
    installBtn.addEventListener("click", async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      await deferredPrompt.userChoice;
      deferredPrompt = null;
      installBtn.hidden = true;
    });
  }
})();