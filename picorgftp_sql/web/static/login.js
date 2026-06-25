const form = document.querySelector("#loginForm");
const message = document.querySelector("#loginMessage");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  message.textContent = "";
  const response = await fetch("/api/login", {
    method: "POST",
    headers: { "X-Requested-With": "XMLHttpRequest" },
    body: new FormData(form),
  });
  if (response.ok) {
    window.location.href = "/";
    return;
  }
  const payload = await response.json().catch(() => ({}));
  message.textContent = payload.detail || "Logowanie nie powiodlo sie.";
});
