// Shows the "time to take your medicine" notification, even when the page is closed.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let d = { title: "Dawai ka time", body: "", url: "/parent", tag: "voxelle" };
  try {
    d = { ...d, ...event.data.json() };
  } catch (_) {}
  event.waitUntil(
    Promise.all([
      self.registration.showNotification(d.title, {
        body: d.body,
        icon: "/static/icon-192.png",
        badge: "/static/icon-192.png",
        tag: d.tag,
        renotify: true,
        requireInteraction: true,
        vibrate: [200, 100, 200],
        data: { url: d.url },
      }),
      self.clients.matchAll({ type: "window" }).then((cs) => cs.forEach((c) => c.postMessage({ type: "push" }))),
    ])
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((cs) => {
      for (const c of cs) {
        if (new URL(c.url).pathname === url && "focus" in c) return c.focus();
      }
      return self.clients.openWindow(url);
    })
  );
});
