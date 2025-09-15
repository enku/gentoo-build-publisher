/* global bootstrap, Chart, barBorderRadius */

const gradientColors = JSON.parse(document.getElementById('gradientColors').textContent);
const machines = JSON.parse(document.getElementById('machines').textContent);

function buildsOverTimeChart() {
  const bot = JSON.parse(document.getElementById('bot').textContent);
  const chartDays = JSON.parse(document.getElementById('chartDays').textContent);
  const datasets = [];

  for (let i = 0; i < bot.length; i += 1) {
    datasets.push({
      label: machines[i],
      data: bot[i],
      backgroundColor: gradientColors[i],
      borderRadius: barBorderRadius,
    });
  }
  const botConfig = {
    type: 'bar',
    data: { labels: chartDays, datasets },
    responsive: true,
    options: {
      animations: false,
      plugins: { legend: { display: false } },
      scales: { y: { ticks: { stepSize: 1 } } },
    },
  };
  const botCtx = document.getElementById('botChart');

  return new Chart(botCtx, botConfig);
}

/* Initialize the dashboard */
function initialize() {
  const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
  popoverTriggerList.map(
    (popoverTriggerEl) => new bootstrap.Popover(popoverTriggerEl),
  );

  buildsOverTimeChart();
}

document.addEventListener('DOMContentLoaded', initialize);
