const demoSteps = ["intake", "agents", "review"];
const demoButtons = document.querySelectorAll("[data-demo-trigger]");
const demoPanels = document.querySelectorAll("[data-demo-panel]");

function setDemoStep(step) {
  if (!demoSteps.includes(step)) return;

  demoButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.demoTrigger === step);
  });
  demoPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.demoPanel === step);
  });
}

demoButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setDemoStep(button.dataset.demoTrigger);
  });
});
