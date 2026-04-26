self.addEventListener("push", (event) => {
  const data = event.data ? event.data.json() : {};
  const title = data.title || "AI News Alert";
  const options = { body: data.body || "Breaking news detected", icon: "/favicon.ico", data: { topic: data.topic || "" } };
  event.waitUntil(self.registration.showNotification(title, options));
});
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const topic = event.notification.data?.topic || "";
  event.waitUntil(clients.openWindow(topic ? `/?topic=${encodeURIComponent(topic)}` : "/"));
});
