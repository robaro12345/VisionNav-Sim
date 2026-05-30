const commandForm = document.getElementById('commandForm');
const commandInput = document.getElementById('commandInput');
const commandResult = document.getElementById('commandResult');
const stateOutput = document.getElementById('stateOutput');
const cameraFeed = document.getElementById('cameraFeed');
const feedPlaceholder = document.getElementById('feedPlaceholder');
const connectionDot = document.getElementById('connectionDot');
const connectionText = document.getElementById('connectionText');
const refreshFeedBtn = document.getElementById('refreshFeedBtn');
const refreshStateBtn = document.getElementById('refreshStateBtn');

let feedVersion = 0;

function setConnection(online, message) {
  connectionDot.classList.toggle('online', online);
  connectionText.textContent = message;
}

async function requestJson(url, options) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const text = await response.text();
  let data = text;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (_) {
    // keep plain text
  }
  if (!response.ok) {
    throw new Error(typeof data === 'string' ? data : JSON.stringify(data));
  }
  return data;
}

async function refreshState() {
  try {
    const state = await requestJson('/state');
    stateOutput.textContent = JSON.stringify(state, null, 2);
    setConnection(true, 'Connected');
  } catch (error) {
    stateOutput.textContent = `Failed to load state: ${error.message}`;
    setConnection(false, 'Disconnected');
  }
}

async function refreshFeed() {
  try {
    const response = await fetch(`/camera/frame.jpg?version=${++feedVersion}`, { cache: 'no-store' });
    if (!response.ok || response.status === 204) {
      cameraFeed.style.display = 'none';
      feedPlaceholder.style.display = 'grid';
      feedPlaceholder.textContent = 'Waiting for camera frames…';
      return;
    }

    const blob = await response.blob();
    const imageUrl = URL.createObjectURL(blob);
    cameraFeed.src = imageUrl;
    cameraFeed.onload = () => {
      feedPlaceholder.style.display = 'none';
      cameraFeed.style.display = 'block';
      URL.revokeObjectURL(imageUrl);
    };
  } catch (error) {
    cameraFeed.style.display = 'none';
    feedPlaceholder.style.display = 'grid';
    feedPlaceholder.textContent = `Camera feed unavailable: ${error.message}`;
  }
}

async function sendCommand(command) {
  commandResult.textContent = 'Sending command…';
  try {
    const result = await requestJson('/command', {
      method: 'POST',
      body: JSON.stringify({ command, state: {} }),
    });
    commandResult.textContent = JSON.stringify(result, null, 2);
    await refreshState();
  } catch (error) {
    commandResult.textContent = `Command failed: ${error.message}`;
  }
}

async function sendDrive(linear_x, angular_z, pulse_duration_ms = 250) {
  try {
    const result = await requestJson('/drive', {
      method: 'POST',
      body: JSON.stringify({ linear_x, angular_z, pulse_duration_ms }),
    });
    commandResult.textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    commandResult.textContent = `Drive failed: ${error.message}`;
  }
}

commandForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const command = commandInput.value.trim();
  if (!command) {
    commandResult.textContent = 'Enter a command first.';
    return;
  }
  sendCommand(command);
});

document.querySelectorAll('[data-action]').forEach((button) => {
  button.addEventListener('click', () => {
    const action = button.dataset.action;
    if (action === 'forward') sendDrive(0.18, 0.0, 900);
    if (action === 'backward') sendDrive(-0.12, 0.0, 900);
    if (action === 'left') sendDrive(0.0, 0.9, 900);
    if (action === 'right') sendDrive(0.0, -0.9, 900);
    if (action === 'stop') sendDrive(0.0, 0.0, 0);
  });
});

refreshFeedBtn.addEventListener('click', refreshFeed);
refreshStateBtn.addEventListener('click', refreshState);

window.addEventListener('keydown', (event) => {
  if (event.target instanceof HTMLTextAreaElement) {
    return;
  }

  if (event.key === 'ArrowUp') sendDrive(0.18, 0.0, 900);
  if (event.key === 'ArrowDown') sendDrive(-0.12, 0.0, 900);
  if (event.key === 'ArrowLeft') sendDrive(0.0, 0.9, 900);
  if (event.key === 'ArrowRight') sendDrive(0.0, -0.9, 900);
  if (event.key === ' ') sendDrive(0.0, 0.0, 0);
});

refreshState();
refreshFeed();
setInterval(refreshState, 3000);
setInterval(refreshFeed, 1500);