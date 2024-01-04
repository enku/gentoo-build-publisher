/* global bootstrap, Chart */

const machineColors = JSON.parse(document.getElementById('machineColors').textContent);
const machines = JSON.parse(document.getElementById('machines').textContent);

function numberize(value) {
  return (value < 1000000000) ? `${value / 1000000}M` : `${value / 1000000000}G`;
}

function machineDistributionChart() {
  const machineDist = JSON.parse(document.getElementById('machineDist').textContent);
  const chartLabels = machines;
  const chartData = machineDist;
  const config = {
    type: 'pie',
    options: {
      plugins: {
        legend: {
          display: false,
        },
      },
    },
    data: {
      labels: chartLabels,
      datasets: [{
        label: 'Build Distribution',
        data: chartData,
        hoverOffset: 4,
        backgroundColor: machineColors,
      }],
    },
  };
  const ctx = document.getElementById('myChart');

  return new Chart(ctx, config);
}

function buildsOverTimeChart() {
  const bot = JSON.parse(document.getElementById('bot').textContent);
  const botDays = JSON.parse(document.getElementById('botDays').textContent);
  const datasets = [];

  for (let i = 0; i < bot.length; i += 1) {
    datasets.push({ label: machines[i], data: bot[i], backgroundColor: machineColors[i] });
  }
  const botConfig = {
    type: 'bar',
    data: { labels: botDays, datasets },
    responsive: true,
    options: {
      plugins: { legend: { display: false } },
      scales: { x: { stacked: true }, y: { stacked: true } },
    },
  };
  const botCtx = document.getElementById('botChart');

  return new Chart(botCtx, botConfig);
}

function packageSizesChart() {
  const packageSizes = JSON.parse(document.getElementById('packageSizes').textContent);
  const sizes = Array.from(machines, (machine) => packageSizes[machine]);
  const pkgSizesConfig = {
    type: 'bar',
    responsive: true,
    data: {
      labels: machines,
      datasets: [{ data: sizes, backgroundColor: machineColors }],
    },
    options: {
      plugins: {
        legend: {
          display: false,
        },
      },
      scales: {
        y: {
          ticks: {
            max: 30,
            stepSize: 5000000000,
            callback: numberize,
          },
        },
      },
    },
  };
  const pkgSizesCtx = document.getElementById('packageSizeChart');

  return new Chart(pkgSizesCtx, pkgSizesConfig);
}

/* Initialize the dashboard */
function initialize() {
  const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
  popoverTriggerList.map(
    (popoverTriggerEl) => new bootstrap.Popover(popoverTriggerEl),
  );

  machineDistributionChart();
  buildsOverTimeChart();
  packageSizesChart();
}

document.addEventListener('DOMContentLoaded', initialize);
