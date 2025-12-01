const blessed = require("blessed");
const { exec, spawn, execSync } = require("child_process"); // <-- Added execSync for better cross-platform checks
const util = require("util");
const os = require("os");

const execPromise = util.promisify(exec);

// Detect if running on Windows
const isWindows = os.platform() === "win32";
const dockerCmd = isWindows ? "wsl docker" : "docker";

// Data cache
let dataCache = {
  containers: [],
  images: [],
  volumes: [],
  networks: [],
  stats: {},
};

// near the top, after the other variables
let containersInterval = null;
let miscInterval = null;

// History for graphs (per container)
let cpuHistory = {};
let memHistory = {};
const maxHistoryPoints = 80;

// Streaming processes
let statsProcess = null;
let logProcess = null;

// State
let selectedContainerIndex = 0;
let selectedImageIndex = 0;
let selectedVolumeIndex = 0;
let selectedNetworkIndex = 0; // ← add this

let logsContent = "";
let logsAutoScroll = true;
let currentTab = 0; // 0=Logs, 1=Stats, 2=Env, 3=Config, 4=Top
const tabNames = ["Logs", "Stats", "Env", "Config", "Top"];

// Create screen
const screen = blessed.screen({
  smartCSR: true,
  title: "Docker TUI",
  fullUnicode: true,
  fastCSR: true,
});

// ==================== LEFT PANELS ====================

// Project box
const projectBox = blessed.box({
  top: 0,
  left: 0,
  width: "40%",
  height: 3,
  label: " [1]-Project ",
  border: { type: "line" },
  style: {
    border: { fg: "cyan" },
    label: { fg: "cyan" },
  },
  content: os.hostname(),
});

// Containers box
const containersBox = blessed.list({
  top: 3,
  left: 0,
  width: "40%",
  height: "30%-3",
  label: " [2]-Containers ",
  border: { type: "line" },
  style: {
    border: { fg: "green" },
    label: { fg: "green" },
    selected: { bg: "blue", fg: "white", bold: true },
    item: { fg: "white" },
  },
  scrollable: true,
  alwaysScroll: true,
  keys: true,
  vi: true,
  mouse: true,
  tags: true,
  interactive: true,
  scrollbar: {
    ch: "│",
    style: { fg: "green" },
  },
});

// Images box
const imagesBox = blessed.list({
  top: "30%",
  left: 0,
  width: "40%",
  height: "25%",
  label: " [3]-Images ",
  border: { type: "line" },
  style: {
    border: { fg: "yellow" },
    label: { fg: "yellow" },
    selected: { bg: "yellow", fg: "black" },
  },
  scrollable: true,
  alwaysScroll: true,
  keys: true,
  vi: true,
  mouse: true,
  tags: true,
});

// Volumes box
const volumesBox = blessed.list({
  top: "55%",
  left: 0,
  width: "40%",
  height: "22%",
  label: " [4]-Volumes ",
  border: { type: "line" },
  style: {
    border: { fg: "magenta" },
    label: { fg: "magenta" },
    selected: { bg: "magenta", fg: "black" },
  },
  scrollable: true,
  alwaysScroll: true,
  keys: true,
  vi: true,
  mouse: true,
  tags: true,
});

// Networks box
const networksBox = blessed.list({
  top: "77%",
  left: 0,
  width: "40%",
  height: "23%-1",
  label: " [5]-Networks ",
  border: { type: "line" },
  style: {
    border: { fg: "blue" },
    label: { fg: "blue" },
    selected: { bg: "blue", fg: "white" },
  },
  scrollable: true,
  alwaysScroll: true,
  keys: true,
  vi: true,
  mouse: true,
  tags: true,
});

// ==================== RIGHT PANEL ====================

// Tab header
const tabHeader = blessed.box({
  top: 0,
  left: "40%",
  width: "60%",
  height: 3,
  border: { type: "line" },
  style: {
    border: { fg: "white" },
  },
  tags: true,
});

// Main content area (right side)
const contentBox = blessed.box({
  top: 3,
  left: "40%",
  width: "60%",
  height: "100%-4",
  border: { type: "line" },
  style: {
    border: { fg: "cyan" },
    label: { fg: "cyan" },
  },
  scrollable: true,
  alwaysScroll: true,
  keys: true,
  vi: true,
  mouse: true,
  tags: true,
  scrollbar: {
    ch: "│",
    style: { fg: "cyan" },
  },
});

// Help bar
const helpBar = blessed.box({
  bottom: 0,
  left: 0,
  width: "100%",
  height: 1,
  tags: true,
  style: {
    fg: "white",
    bg: "blue",
  },
});

// Append all elements
screen.append(projectBox);
screen.append(containersBox);
screen.append(imagesBox);
screen.append(volumesBox);
screen.append(networksBox);
screen.append(tabHeader);
screen.append(contentBox);
screen.append(helpBar);

function reselectByName(list, dataArray, selectedName) {
  if (!selectedName) return 0;
  const idx = dataArray.findIndex(
    (d) => d.name === selectedName || d.id === selectedName,
  );
  return Math.max(0, idx);
}

/* ---------- stable list update ---------- */
function updateListStable(list, items, prevIndex = 0) {
  const wasFocused = screen.focused === list;
  list.setItems(items);
  const newIndex = Math.min(prevIndex, items.length - 1);
  list.select(newIndex);
  if (wasFocused) list.focus();
  screen.render();
  return newIndex;
}
/* ---------- Helper: only act if containers list is focused ---------- */
function withFocusedContainer(fn) {
  return () => {
    if (screen.focused !== containersBox) return; // ignore if not in containers
    const c = dataCache.containers[selectedContainerIndex];
    if (c) fn(c);
  };
}
// ==================== TAB HEADER ====================

function updateTabHeader() {
  let header = "";
  tabNames.forEach((name, index) => {
    if (index === currentTab) {
      header += `{cyan-fg}{bold} ${name} {/bold}{/cyan-fg}`;
    } else {
      header += `{gray-fg} ${name} {/gray-fg}`;
    }
    if (index < tabNames.length - 1) {
      header += "{white-fg}-{/white-fg}";
    }
  });
  tabHeader.setContent(header);
}

function updateHelpBar() {
  const container = dataCache.containers[selectedContainerIndex];
  const isRunning = container && container.state === "running";

  let help = " {bold}q{/}:Quit {bold}←→{/}:Tabs {bold}↑↓{/}:Nav ";

  if (container) {
    if (isRunning) {
      help += "{bold}s{/}:Stop {bold}r{/}:Restart {bold}e{/}:Exec ";
    } else {
      help += "{bold}s{/}:Start ";
    }
    help += "{bold}d{/}:Delete ";
  }

  help += "{bold}l{/}:FullLogs {bold}a{/}:AutoScroll {bold}R{/}:Refresh";

  helpBar.setContent(help);
}

// ==================== DOCKER COMMANDS ====================

async function getContainers() {
  try {
    const { stdout } = await execPromise(
      `${dockerCmd} ps -a --format "{{.Names}}|{{.Status}}|{{.ID}}|{{.Image}}|{{.Ports}}|{{.State}}"`,
      { timeout: 5000 },
    );
    const lines = stdout
      .trim()
      .split("\n")
      .filter((l) => l);
    if (lines.length === 0 || lines[0] === "") return [];
    return lines.map((line) => {
      const [name, status, id, image, ports, state] = line.split("|");
      return {
        name,
        status,
        id: id ? id.substring(0, 12) : "N/A",
        image,
        ports: ports || "",
        state: state || "unknown",
      };
    });
  } catch (error) {
    return dataCache.containers || [];
  }
}

async function getImages() {
  try {
    const { stdout } = await execPromise(
      `${dockerCmd} images --format "{{.Repository}}|{{.Tag}}|{{.Size}}|{{.ID}}"`,
      { timeout: 5000 },
    );
    const lines = stdout
      .trim()
      .split("\n")
      .filter((l) => l);
    if (lines.length === 0 || lines[0] === "") return [];
    return lines.map((line) => {
      const [repo, tag, size, id] = line.split("|");
      return { repo, tag, size, id: id ? id.substring(0, 12) : "N/A" };
    });
  } catch (error) {
    return [];
  }
}

async function getVolumes() {
  try {
    const { stdout } = await execPromise(
      `${dockerCmd} volume ls --format "{{.Driver}}|{{.Name}}"`,
      { timeout: 5000 },
    );
    return stdout
      .trim()
      .split("\n")
      .filter((l) => l)
      .map((l) => {
        const [driver, name] = l.split("|");
        return { driver: driver || "local", name: name || "N/A" };
      });
  } catch (error) {
    return [];
  }
}

async function getNetworks() {
  try {
    const { stdout } = await execPromise(
      `${dockerCmd} network ls --format "{{.Driver}}|{{.Name}}"`,
      { timeout: 5000 },
    );
    return stdout
      .trim()
      .split("\n")
      .filter((l) => l)
      .map((l) => {
        const [driver, name] = l.split("|");
        return { driver: driver || "bridge", name: name || "N/A" };
      });
  } catch (error) {
    return [];
  }
}

async function getContainerEnv(containerName) {
  try {
    const { stdout } = await execPromise(
      `${dockerCmd} inspect --format "{{range .Config.Env}}{{println .}}{{end}}" ${containerName}`,
      { timeout: 5000 },
    );
    return stdout
      .trim()
      .split("\n")
      .filter((l) => l);
  } catch (error) {
    return [];
  }
}

async function getContainerTop(containerName) {
  try {
    const { stdout } = await execPromise(`${dockerCmd} top ${containerName}`, {
      timeout: 5000,
    });
    return stdout.trim();
  } catch (error) {
    return "Container not running or top not available";
  }
}

async function getContainerInspect(containerName) {
  try {
    const { stdout } = await execPromise(
      `${dockerCmd} inspect ${containerName}`,
      { timeout: 5000 },
    );
    return JSON.parse(stdout)[0];
  } catch (error) {
    return null;
  }
}

// ==================== STATS STREAMING ====================

// ==================== 1.  REPLACE startStatsStream ====================
function startStatsStream() {
  if (statsProcess) {
    try {
      statsProcess.kill();
    } catch (_) {}
  }

  const cmdParts = dockerCmd.split(" ");
  const baseCmd = cmdParts[0];
  const args = [
    ...cmdParts.slice(1),
    "stats",
    "--no-stream=false", // ensure streaming
    "--format",
    "table {{.Name}}\t{{.CPUPerc}}\t{{.MemPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}\t{{.PIDs}}",
  ];

  statsProcess = spawn(baseCmd, args, { stdio: ["ignore", "pipe", "pipe"] });

  let buffer = "";
  statsProcess.stdout.on("data", (chunk) => {
    buffer += chunk.toString();
    const lines = buffer.split("\n");
    buffer = lines.pop(); // keep incomplete line

    for (const line of lines) {
      if (!line.trim() || line.startsWith("NAME")) continue; // skip header

      const parts = line.split(/\s{2,}|\t/); // split on 2+ spaces or tab
      if (parts.length < 7) continue;

      const [name, cpuStr, memStr, memUsage, netIO, blockIO, pids] = parts;
      if (!name) continue;

      const cpuVal = parseFloat(cpuStr?.replace("%", "")) || 0;
      const memVal = parseFloat(memStr?.replace("%", "")) || 0;

      dataCache.stats[name] = {
        cpu: cpuVal,
        mem: memVal,
        memUsage: memUsage || "N/A",
        netIO: netIO || "N/A",
        blockIO: blockIO || "N/A",
        pids: pids || "N/A",
      };

      // Seed history arrays if empty so graph starts immediately
      if (!cpuHistory[name]) cpuHistory[name] = [];
      if (!memHistory[name]) memHistory[name] = [];

      cpuHistory[name].push(cpuVal);
      memHistory[name].push(memVal);

      if (cpuHistory[name].length > maxHistoryPoints) cpuHistory[name].shift();
      if (memHistory[name].length > maxHistoryPoints) memHistory[name].shift();
    }

    if (currentTab === 1) updateStatsTab();
  });

  statsProcess.stderr.on("data", (d) => {
    // Optionally log to a file or ignore
  });

  statsProcess.on("error", () => {});
  statsProcess.on("close", () => {
    setTimeout(() => {
      if (!statsProcess || statsProcess.killed) startStatsStream();
    }, 2000);
  });
}

/* =========================================================
      Braille line chart – thickened + auto-zoom
      ========================================================= */
function smoothChart(data, height = 12, width = 60, color = "cyan") {
  if (!data || data.length < 2) {
    return (
      Array(height).fill(" ".repeat(width)).join("\n") +
      `\n{${color}-fg}0.00 % (waiting…){/${color}-fg}`
    );
  }

  const slice = data.slice(-width);

  /* ---- auto-zoom: use actual min/max, not 0-100 ---- */
  const max = Math.max(...slice);
  const min = Math.min(...slice);
  const range = max - min || 1;

  /* Braille dot map (2×4) */
  const dots = [
    [0x01, 0x08],
    [0x02, 0x10],
    [0x04, 0x20],
    [0x40, 0x80],
  ];

  const pxW = width * 2;
  const pxH = height * 4;
  const canvas = Array.from({ length: pxH }, () => Array(pxW).fill(0));

  /* Map values to pixel rows */
  const y = (v) => Math.round(pxH - 1 - ((v - min) / range) * (pxH - 1));

  /* ---- draw thickened line (2 px wide) ---- */
  for (let i = 0; i < slice.length - 1; i++) {
    const x0 = Math.round((i / (slice.length - 1)) * (pxW - 1));
    const x1 = Math.round(((i + 1) / (slice.length - 1)) * (pxW - 1));
    const y0 = y(slice[i]);
    const y1 = y(slice[i + 1]);

    const steps = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0)) * 2;
    for (let s = 0; s <= steps; s++) {
      const t = s / steps;
      const sx = Math.round(x0 + (x1 - x0) * t);
      const sy = Math.round(y0 + (y1 - y0) * t);

      /* paint a 2×2 square for thickness */
      for (let dy = 0; dy <= 1; dy++) {
        for (let dx = 0; dx <= 1; dx++) {
          const cx = sx + dx;
          const cy = sy + dy;
          if (cx >= 0 && cx < pxW && cy >= 0 && cy < pxH) {
            canvas[cy][cx] = 1;
          }
        }
      }
    }
  }

  /* ---- convert to Braille ---- */
  const rows = [];
  for (let row = 0; row < pxH; row += 4) {
    let line = "";
    for (let col = 0; col < pxW; col += 2) {
      let code = 0x2800;
      for (let dy = 0; dy < 4; dy++) {
        for (let dx = 0; dx < 2; dx++) {
          if (canvas[row + dy]?.[col + dx]) {
            code |= dots[dy][dx];
          }
        }
      }
      line += String.fromCharCode(code);
    }

    const val = max - (row / 4 / (height - 1)) * range;
    rows.push(
      `${val.toFixed(2).padStart(6)} │{${color}-fg}${line}{/${color}-fg}`,
    );
  }

  rows.push("       └" + "─".repeat(width));
  const cur = slice[slice.length - 1];
  rows.push(
    `\n{${color}-fg}        ${cur.toFixed(2)} %  (${slice.length * 2}s){/${color}-fg}`,
  );

  return rows.join("\n");
}

/* =========================================================
   1.  Colour helpers
   ========================================================= */
const cpuGrad = ["#0a3d62", "#1e90ff", "#00d4ff"]; // dark → light cyan
const memGrad = ["#0a4d0a", "#00b300", "#00ff00"]; // dark → light green

function hexToBlessed(hex) {
  // Very small palette map for Blessed
  const map = {
    "#0a3d62": "blue",
    "#1e90ff": "cyan",
    "#00d4ff": "bright-cyan",
    "#0a4d0a": "green",
    "#00b300": "bright-green",
    "#00ff00": "bright-white",
  };
  return map[hex] || "white";
}

/* =========================================================
   2.  Horizontal filled bar with gradient
   ========================================================= */
function gradientBar(value, max, width = 50) {
  const filled = Math.max(
    0,
    Math.min(width, Math.round((value / max) * width)),
  );
  let bar = "";
  for (let i = 0; i < width; i++) {
    const ratio = i / (width - 1);
    const colorIdx = Math.floor(ratio * (cpuGrad.length - 1));
    const color = hexToBlessed(cpuGrad[colorIdx]);
    const ch = i < filled ? "█" : " ";
    bar += `{${color}-fg}${ch}{/${color}-fg}`;
  }
  return bar;
}

/* =========================================================
   3.  Smooth “curvy” silhouette (Unicode half-blocks)
   ========================================================= */
function smoothSpark(nums, width = 50, color = "cyan") {
  if (!nums || nums.length < 2) return " ".repeat(width);
  const slice = nums.slice(-width);
  const max = Math.max(...slice, 1);
  const min = Math.min(...slice, 0);
  const range = max - min || 1;

  const rows = 4; // 4 rows of half-blocks gives 8 vertical steps
  const canvas = Array.from({ length: rows }, () => Array(width).fill(" "));

  for (let x = 0; x < slice.length; x++) {
    const val = slice[x];
    const yNorm = (val - min) / range; // 0..1
    const yRow = Math.floor(yNorm * (rows * 2)); // 0..7 (8 steps)

    const full = Math.floor(yRow / 2);
    const half = yRow % 2;

    for (let r = 0; r < rows; r++) {
      if (r < rows - full - 1) continue;
      if (r === rows - full - 1 && half) {
        canvas[r][x] = "▄"; // lower half block
      } else {
        canvas[r][x] = "█";
      }
    }
  }

  return canvas
    .map((row) => `{${color}-fg}${row.join("")}{/${color}-fg}`)
    .join("\n       ");
}

/* =========================================================
   4.  Human-readable bytes (unchanged)
   ========================================================= */
function humanBytes(n) {
  const units = ["B", "kB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(1)}${units[i]}`;
}
// // ==================== GRAPH RENDERING (Lazydocker style) ====================
// (Removed commented-out graph code for brevity)

// ==================== CONTAINER ACTIONS ====================

async function startContainer(name) {
  try {
    await execPromise(`${dockerCmd} start ${name}`, { timeout: 30000 });
    showNotification(`Started ${name}`, "green");
    await updateAll();
  } catch (error) {
    showNotification(`Failed to start: ${error.message}`, "red");
  }
}

async function stopContainer(name) {
  try {
    await execPromise(`${dockerCmd} stop ${name}`, { timeout: 30000 });
    showNotification(`Stopped ${name}`, "yellow");
    await updateAll();
  } catch (error) {
    showNotification(`Failed to stop: ${error.message}`, "red");
  }
}

async function restartContainer(name) {
  try {
    await execPromise(`${dockerCmd} restart ${name}`, { timeout: 60000 });
    showNotification(`Restarted ${name}`, "green");
    await updateAll();
  } catch (error) {
    showNotification(`Failed to restart: ${error.message}`, "red");
  }
}

async function deleteContainer(name) {
  try {
    await execPromise(`${dockerCmd} rm -f ${name}`, { timeout: 30000 });
    showNotification(`Deleted ${name}`, "red");
    await updateAll();
  } catch (error) {
    showNotification(`Failed to delete: ${error.message}`, "red");
  }
}

function showNotification(message, color = "green") {
  const notification = blessed.box({
    top: "center",
    left: "center",
    width: Math.min(message.length + 6, 60),
    height: 3,
    content: ` ${message} `,
    border: { type: "line" },
    style: {
      border: { fg: color },
      fg: color,
      bg: "black",
    },
  });

  screen.append(notification);
  screen.render();

  setTimeout(() => {
    screen.remove(notification);
    screen.render();
  }, 2000);
}

// ==================== LOGS ====================

function showContainerLogs(containerName, tail = "200") {
  if (!containerName) return;

  stopLogStream();

  logsContent = "";
  contentBox.setContent("{cyan-fg}Loading logs...{/cyan-fg}");
  screen.render();

  const cmdParts = dockerCmd.split(" ");
  const baseCmd = cmdParts[0];
  const args = [
    ...cmdParts.slice(1),
    "logs",
    "-f",
    "--tail",
    tail,
    containerName,
  ];

  logProcess = spawn(baseCmd, args);

  logProcess.stdout.on("data", (data) => {
    logsContent += data.toString();
    if (logsContent.length > 100000) {
      logsContent = logsContent.slice(-100000);
    }
    if (currentTab === 0) {
      contentBox.setContent(logsContent);
      if (logsAutoScroll) {
        contentBox.setScrollPerc(100);
      }
      screen.render();
    }
  });

  logProcess.stderr.on("data", (data) => {
    logsContent += data.toString();
    if (logsContent.length > 100000) {
      logsContent = logsContent.slice(-100000);
    }
    if (currentTab === 0) {
      contentBox.setContent(logsContent);
      if (logsAutoScroll) {
        contentBox.setScrollPerc(100);
      }
      screen.render();
    }
  });

  logProcess.on("error", (err) => {
    logsContent += `\n{red-fg}Error: ${err.message}{/red-fg}`;
    if (currentTab === 0) {
      contentBox.setContent(logsContent);
      screen.render();
    }
  });
}

function stopLogStream() {
  if (logProcess) {
    logProcess.kill();
    logProcess = null;
  }
}

// ==================== EXEC (Fixed for non-TTY) ====================

function execIntoContainer(containerName) {
  if (!containerName) return;

  const container = dataCache.containers.find((c) => c.name === containerName);
  if (!container || container.state !== "running") {
    showNotification("Container must be running to exec", "red");
    return;
  }

  // Use a simpler approach - open external terminal
  showNotification("Opening terminal... (use external window)", "cyan");

  // For Windows with WSL
  if (isWindows) {
    const cmd = `start wsl docker exec -it ${containerName} sh -c "if [ -x /bin/bash ]; then exec /bin/bash; else exec /bin/sh; fi"`;
    exec(cmd, (error) => {
      if (error) {
        showNotification(`Exec failed: ${error.message}`, "red");
      }
    });
  } else {
    // For Linux/Mac - try to open in new terminal
    const terminals = [
      `x-terminal-emulator -e docker exec -it ${containerName} sh`,
      `gnome-terminal -- docker exec -it ${containerName} sh`,
      `xterm -e docker exec -it ${containerName} sh`,
      `konsole -e docker exec -it ${containerName} sh`,
    ];

    let opened = false;
    for (const termCmd of terminals) {
      try {
        exec(termCmd, (error) => {
          if (!error) opened = true;
        });
        if (opened) break;
      } catch (e) {
        continue;
      }
    }

    if (!opened) {
      showNotification(
        "Run: docker exec -it " + containerName + " sh",
        "yellow",
      );
    }
  }
}

// ==================== TAB CONTENT UPDATES ====================

function updateLogsTab() {
  const container = dataCache.containers[selectedContainerIndex];
  if (!container) {
    contentBox.setContent("{yellow-fg}No container selected{/yellow-fg}");
    return;
  }
  contentBox.setContent(logsContent || "{gray-fg}No logs yet...{/gray-fg}");
  screen.render();
}

// ==================== 2.  REPLACE updateStatsTab ====================
function updateStatsTab() {
  const c = dataCache.containers[selectedContainerIndex];
  if (!c) {
    contentBox.setContent("{yellow-fg}No container selected{/yellow-fg}");
    screen.render();
    return;
  }

  const stat = dataCache.stats[c.name] || {};
  const running = c.state === "running";

  if (!cpuHistory[c.name]) cpuHistory[c.name] = [0];
  if (!memHistory[c.name]) memHistory[c.name] = [0];

  const cpu = cpuHistory[c.name];
  const mem = memHistory[c.name];

  let out = `{bold}{cyan-fg}Stats: ${c.name}{/cyan-fg}{/bold}\n`;
  out += `{gray-fg}${"─".repeat(60)}{/gray-fg}\n\n`;

  if (!running) {
    out += "{gray-fg}Container is not running{/gray-fg}\n";
    out += "{gray-fg}Press [s] to start{/gray-fg}\n";
    contentBox.setContent(out);
    screen.render();
    return;
  }

  /* CPU chart */
  out += smoothChart(cpu, 12, 55, "cyan") + "\n\n";
  /* MEM chart */
  out += smoothChart(mem, 12, 55, "green") + "\n\n";

  /* Other metrics (unchanged) */
  // NOTE: This logic assumes 'X B / Y B' format from docker stats,
  // and extracts the number before the unit. Docker output is sometimes complex
  // but this is the best effort given the structure.
  const [rx, tx] = (stat.netIO || "0B / 0B").split(" / ");
  const [read, write] = (stat.blockIO || "0B / 0B").split(" / ");

  const parseBytes = (ioStr) => {
    const match = ioStr.match(/^([\d.]+)/);
    return match ? parseFloat(match[1]) : 0;
  };

  out += `{bold}{yellow-fg}PIDs:{/yellow-fg}{/bold}     ${stat.pids || "N/A"}\n`;
  out += `{bold}{blue-fg}Net RX:{/blue-fg}{/bold}   ${humanBytes(parseBytes(rx))}\n`;
  out += `{bold}{blue-fg}Net TX:{/blue-fg}{/bold}   ${humanBytes(parseBytes(tx))}\n`;
  out += `{bold}{magenta-fg}Disk R:{/magenta-fg}{/bold}   ${humanBytes(parseBytes(read))}\n`;
  out += `{bold}{magenta-fg}Disk W:{/magenta-fg}{/bold}   ${humanBytes(parseBytes(write))}\n`;

  contentBox.setContent(out);
  screen.render();
}

async function updateEnvTab() {
  const container = dataCache.containers[selectedContainerIndex];

  if (!container) {
    contentBox.setContent("{yellow-fg}No container selected{/yellow-fg}");
    return;
  }

  contentBox.setContent("{cyan-fg}Loading environment variables...{/cyan-fg}");
  screen.render();

  const envVars = await getContainerEnv(container.name);

  let content = `{bold}{cyan-fg}Environment Variables: ${container.name}{/cyan-fg}{/bold}\n`;
  content += `{gray-fg}${"─".repeat(55)}{/gray-fg}\n\n`;

  if (envVars.length === 0) {
    content += "{yellow-fg}No environment variables found{/yellow-fg}\n";
  } else {
    envVars.forEach((env) => {
      const eqIndex = env.indexOf("=");
      if (eqIndex > 0) {
        const key = env.substring(0, eqIndex);
        const value = env.substring(eqIndex + 1);
        content += `{bold}${key}{/bold}={green-fg}${value}{/green-fg}\n`;
      } else {
        content += `${env}\n`;
      }
    });
  }

  contentBox.setContent(content);
  screen.render();
}

async function updateConfigTab() {
  const container = dataCache.containers[selectedContainerIndex];

  if (!container) {
    contentBox.setContent("{yellow-fg}No container selected{/yellow-fg}");
    return;
  }

  contentBox.setContent("{cyan-fg}Loading configuration...{/cyan-fg}");
  screen.render();

  const inspect = await getContainerInspect(container.name);

  let content = `{bold}{cyan-fg}Configuration: ${container.name}{/cyan-fg}{/bold}\n`;
  content += `{gray-fg}${"─".repeat(55)}{/gray-fg}\n\n`;

  if (!inspect) {
    content += "{red-fg}Failed to get container configuration{/red-fg}\n";
  } else {
    // Basic info
    content += `{bold}ID:{/bold} ${inspect.Id?.substring(0, 12) || "N/A"}\n`;
    content += `{bold}Created:{/bold} ${inspect.Created || "N/A"}\n`;
    content += `{bold}Image:{/bold} ${inspect.Config?.Image || "N/A"}\n`;
    content += `{bold}Entrypoint:{/bold} ${JSON.stringify(inspect.Config?.Entrypoint) || "N/A"}\n`;
    content += `{bold}Cmd:{/bold} ${JSON.stringify(inspect.Config?.Cmd) || "N/A"}\n`;
    content += `{bold}WorkingDir:{/bold} ${inspect.Config?.WorkingDir || "/"}\n\n`;

    // Network settings
    content += `{bold}{yellow-fg}Network Settings:{/yellow-fg}{/bold}\n`;
    const networks = inspect.NetworkSettings?.Networks || {};
    for (const [netName, netConfig] of Object.entries(networks)) {
      content += `  {bold}${netName}:{/bold}\n`;
      content += `    IP: ${netConfig.IPAddress || "N/A"}\n`;
      content += `    Gateway: ${netConfig.Gateway || "N/A"}\n`;
      content += `    MAC: ${netConfig.MacAddress || "N/A"}\n`;
    }
    content += "\n";

    // Port bindings
    content += `{bold}{green-fg}Port Bindings:{/green-fg}{/bold}\n`;
    const ports = inspect.NetworkSettings?.Ports || {};
    if (Object.keys(ports).length === 0) {
      content += "  {gray-fg}No ports exposed{/gray-fg}\n";
    } else {
      for (const [containerPort, hostBindings] of Object.entries(ports)) {
        if (hostBindings) {
          hostBindings.forEach((binding) => {
            content += `  {cyan-fg}${binding.HostIp || "0.0.0.0"}:${binding.HostPort}{/cyan-fg} -> ${containerPort}\n`;
          });
        } else {
          content += `  ${containerPort} (not bound)\n`;
        }
      }
    }
    content += "\n";

    // Mounts
    content += `{bold}{magenta-fg}Mounts:{/magenta-fg}{/bold}\n`;
    const mounts = inspect.Mounts || [];
    if (mounts.length === 0) {
      content += "  {gray-fg}No mounts{/gray-fg}\n";
    } else {
      mounts.forEach((mount) => {
        content += `  ${mount.Type}: ${mount.Source || "N/A"}\n`;
        content += `    -> ${mount.Destination}\n`;
      });
    }
    content += "\n";

    // Resource limits
    content += `{bold}{red-fg}Resource Limits:{/red-fg}{/bold}\n`;
    const hostConfig = inspect.HostConfig || {};
    content += `  CPU Shares: ${hostConfig.CpuShares || "default"}\n`;
    content += `  Memory Limit: ${hostConfig.Memory ? (hostConfig.Memory / 1024 / 1024).toFixed(0) + "MB" : "unlimited"}\n`;
    content += `  Restart Policy: ${hostConfig.RestartPolicy?.Name || "no"}\n`;
  }

  contentBox.setContent(content);
  screen.render();
}

async function updateTopTab() {
  const container = dataCache.containers[selectedContainerIndex];

  if (!container) {
    contentBox.setContent("{yellow-fg}No container selected{/yellow-fg}");
    return;
  }

  contentBox.setContent("{cyan-fg}Loading processes...{/cyan-fg}");
  screen.render();

  let content = `{bold}{cyan-fg}Top Processes: ${container.name}{/cyan-fg}{/bold}\n`;
  content += `{gray-fg}${"─".repeat(55)}{/gray-fg}\n\n`;

  if (container.state === "running") {
    const top = await getContainerTop(container.name);
    content += `{green-fg}${top}{/green-fg}\n\n`;
  } else {
    content += "{gray-fg}Container is not running{/gray-fg}\n\n";
  }

  // Show top for all other running containers
  content += `{bold}{yellow-fg}All Running Containers:{/yellow-fg}{/bold}\n`;
  content += `{gray-fg}${"─".repeat(55)}{/gray-fg}\n\n`;

  // NOTE: This nested loop will significantly slow down the UI.
  // A proper TUI implementation should not block the rendering thread with multiple
  // execPromise calls. Keeping it for functional completeness but noting the performance risk.
  for (const c of dataCache.containers) {
    if (c.name !== container.name && c.state === "running") {
      content += `{bold}${c.name}:{/bold}\n`;
      const t = await getContainerTop(c.name);
      content += t + "\n\n";
    }
  }

  contentBox.setContent(content);
  screen.render();
}

// Switch tab and update content
async function switchTab(tabIndex) {
  currentTab = tabIndex;
  updateTabHeader();
  await updateCurrentTab();
  screen.render();
}

async function updateCurrentTab() {
  const container = dataCache.containers[selectedContainerIndex];

  // If the container is still null, but the index is 0, it means no containers exist.
  if (!container && dataCache.containers.length === 0) {
    contentBox.setContent(
      "{yellow-fg}No containers available. Start Docker or create one.{/yellow-fg}",
    );
    screen.render();
    return;
  }

  // Handle case where selection index is valid, but container data hasn't loaded yet.
  if (!container) return;

  // Special handling for Logs tab: if logs aren't streaming for the selected container, start them.
  if (
    currentTab === 0 &&
    (!logProcess || !logProcess.spawnargs.includes(container.name))
  ) {
    showContainerLogs(container.name, "100");
    // Don't fall through to updateLogsTab immediately, let the stream populate 'logsContent'
    return;
  }

  // Stop log stream if switching away from logs tab
  if (currentTab !== 0) {
    stopLogStream();
  }

  switch (currentTab) {
    case 0:
      updateLogsTab();
      break;
    case 1:
      updateStatsTab();
      break;
    case 2:
      await updateEnvTab();
      break;
    case 3:
      await updateConfigTab();
      break;
    case 4:
      await updateTopTab();
      break;
  }
  screen.render();
}

// ==================== UPDATE FUNCTIONS ====================
/* ---------- Stable list update - only rebuild when data changes ---------- */
function updateListIfChanged(list, newData, formatFn, selectedIndexRef) {
  // Defensive check for empty data array
  if (!newData || newData.length === 0) {
    const defaultItem = ["{yellow-fg}No items{/yellow-fg}"];
    if (list.items.length !== 1 || list.items[0].content !== defaultItem[0]) {
      list.setItems(defaultItem);
      list.select(0);
      screen.render();
    }
    selectedIndexRef[0] = 0;
    return;
  }

  const currentItems = list.items;
  const newItems = newData.map(formatFn);

  // Check if items actually changed
  const hasChanged =
    currentItems.length !== newItems.length ||
    currentItems.some((item, i) => item.content !== newItems[i]);

  if (hasChanged) {
    const wasFocused = screen.focused === list;
    const currentSelection = list.selected;

    list.setItems(newItems);

    // Restore selection, but ensure it's within bounds
    const newSelection = Math.min(currentSelection, newItems.length - 1);
    list.select(Math.max(0, newSelection));

    if (wasFocused) list.focus();
    screen.render();

    // Update the external index reference
    selectedIndexRef[0] = Math.max(0, newSelection);
  } else {
    // If no change, ensure the external index ref is consistent with the list's actual selection
    selectedIndexRef[0] = list.selected;
  }
}

/* ---------- Containers ---------- */
async function updateContainers() {
  try {
    const containers = await getContainers();

    // Only update cache if data changed
    const dataChanged =
      JSON.stringify(containers) !== JSON.stringify(dataCache.containers);
    // Optimization: avoid full deep compare. Docker stats update frequently,
    // so we skip the dataChanged check for containers and always update the list.

    dataCache.containers = containers;

    const formatContainer = (c) => {
      const stat = dataCache.stats[c.name] || { cpu: 0, mem: 0 };
      const isRunning = c.state === "running";
      const isPaused = c.status.includes("Paused");
      let status = isRunning
        ? isPaused
          ? "{yellow-fg}paused{/yellow-fg}"
          : "{green-fg}running{/green-fg}"
        : "{red-fg}exited{/red-fg}";
      if (c.status.includes("healthy"))
        status = "{green-fg}running (healthy){/green-fg}";

      const name = c.name.substring(0, 18).padEnd(18);
      const cpu = isRunning ? `${stat.cpu.toFixed(2)}%`.padStart(7) : "      -";
      const ports = c.ports ? c.ports.substring(0, 12) : "";
      return `${status.padEnd(25)} {bold}${name}{/bold} ${cpu} {cyan-fg}${ports}{/cyan-fg}`;
    };

    const indexRef = [selectedContainerIndex];
    updateListIfChanged(containersBox, containers, formatContainer, indexRef);
    selectedContainerIndex = indexRef[0];
    updateHelpBar();
  } catch (err) {
    containersBox.setItems([`{red-fg}Error: ${err.message}{/red-fg}`]);
  }
}

/* ---------- Images ---------- */
async function updateImages() {
  try {
    const images = await getImages();

    const dataChanged =
      JSON.stringify(images) !== JSON.stringify(dataCache.images);
    if (!dataChanged) return;

    dataCache.images = images;

    const formatImage = (img) => {
      const name = img.repo.substring(0, 20).padEnd(20);
      const tag = img.tag.substring(0, 10).padEnd(10);
      const size = img.size.padEnd(10);
      return `${name} {yellow-fg}${tag}{/yellow-fg} ${size}`;
    };

    const indexRef = [selectedImageIndex];
    updateListIfChanged(imagesBox, images, formatImage, indexRef);
    selectedImageIndex = indexRef[0];
  } catch {
    imagesBox.setItems(["{red-fg}Error{/red-fg}"]);
  }
}

/* ---------- Volumes ---------- */
async function updateVolumes() {
  try {
    const volumes = await getVolumes();

    const dataChanged =
      JSON.stringify(volumes) !== JSON.stringify(dataCache.volumes);
    if (!dataChanged) return;

    dataCache.volumes = volumes;

    const formatVolume = (v) =>
      `{magenta-fg}${v.driver.padEnd(8)}{/magenta-fg} ${v.name}`;

    const indexRef = [selectedVolumeIndex];
    updateListIfChanged(volumesBox, volumes, formatVolume, indexRef);
    selectedVolumeIndex = indexRef[0];
  } catch {
    volumesBox.setItems(["{red-fg}Error{/red-fg}"]);
  }
}

/* ---------- Networks ---------- */
async function updateNetworks() {
  try {
    const networks = await getNetworks();

    const dataChanged =
      JSON.stringify(networks) !== JSON.stringify(dataCache.networks);
    if (!dataChanged) return;

    dataCache.networks = networks;

    const formatNetwork = (n) =>
      `{blue-fg}${n.driver.padEnd(8)}{/blue-fg} ${n.name}`;

    const indexRef = [selectedNetworkIndex];
    updateListIfChanged(networksBox, networks, formatNetwork, indexRef);
    selectedNetworkIndex = indexRef[0];
  } catch {
    networksBox.setItems(["{red-fg}Error{/red-fg}"]);
  }
}

async function updateAll() {
  try {
    await Promise.all([
      updateContainers(),
      updateImages(),
      updateVolumes(),
      updateNetworks(),
    ]);
    await updateCurrentTab();
    screen.render();
  } catch (error) {
    screen.render();
  }
}

// ==================== KEYBOARD HANDLERS ====================

// Quit
screen.key(["q", "C-c"], () => {
  cleanup();
  process.exit(0);
});

// Refresh
screen.key(["S-r"], () => updateAll());

// Tab navigation with arrow keys
screen.key(["right"], async () => {
  currentTab = (currentTab + 1) % tabNames.length;
  updateTabHeader();
  await updateCurrentTab();
});

screen.key(["left"], async () => {
  currentTab = (currentTab - 1 + tabNames.length) % tabNames.length;
  updateTabHeader();
  await updateCurrentTab();
});

/* ----------------------------------------------------------
   Let each list handle its own navigation.
   We only need to react when the selection *inside* a list
   actually changes.
---------------------------------------------------------- */

// When user switches panels with 1-5
screen.key(["2"], () => {
  containersBox.focus();
  screen.render();
});
screen.key(["3"], () => {
  imagesBox.focus();
  screen.render();
});
screen.key(["4"], () => {
  volumesBox.focus();
  screen.render();
});
screen.key(["5"], () => {
  networksBox.focus();
  screen.render();
});

/* =========================================================
   Helpers: run in a new terminal window / tab
   ========================================================= */
/* =========================================================
      Open a new terminal window / tab
      ========================================================= */
function spawnNewWindow(cmd, label) {
  const plat = os.platform();

  /* ---------- Windows ---------- */
  if (plat === "win32") {
    // 1. Try Windows Terminal (wt.exe)
    try {
      execSync("where wt", { stdio: "ignore" });
      exec(`wt new-tab --title "${label}" cmd /k ${cmd}`);
      return;
    } catch (e) {
      /* ignore */
    }

    // 2. Try Git-Bash’s mintty
    const bashPath =
      process.env.SHELL || "C:\\Program Files\\Git\\bin\\bash.exe";
    try {
      execSync("where mintty", { stdio: "ignore" });
      exec(`mintty -t "${label}" -e ${bashPath} -c "${cmd}"`);
      return;
    } catch (e) {
      /* ignore */
    }

    // 3. Fallback to regular cmd
    exec(`start cmd /k ${cmd}`);
    return;
  }

  /* ---------- macOS ---------- */
  if (plat === "darwin") {
    exec(`osascript -e 'tell application "Terminal" to do script "${cmd}"'`);
    return;
  }

  /* ---------- Linux / WSL ---------- */
  const terms = [
    `x-terminal-emulator -e ${cmd}`,
    `gnome-terminal -- ${cmd}`,
    `xterm -e ${cmd}`,
    `konsole -e ${cmd}`,
  ];
  const term = terms.find((t) => {
    try {
      execSync(`which ${t.split(" ")[0].trim()}`, { stdio: "ignore" });
      return true;
    } catch {
      return false;
    }
  });
  if (term) {
    exec(term);
  } else {
    showNotification(
      "No GUI terminal found – use in-shell shortcut instead",
      "yellow",
    );
  }
}

/* ---------- helper: re-select by name ---------- */
function reselectByName(list, dataArray, selectedName) {
  if (!selectedName) return 0;
  const idx = dataArray.findIndex(
    (d) => d.name === selectedName || d.id === selectedName,
  );
  return Math.max(0, idx);
}
/* =========================================================
   Context-aware shortcuts
   ========================================================= */
function withFocusedContainer(fn) {
  return () => {
    if (screen.focused !== containersBox) return;
    const c = dataCache.containers[selectedContainerIndex];
    if (c) fn(c);
  };
}

/* ---------- Container actions ---------- */
screen.key(
  ["s"],
  withFocusedContainer((c) =>
    c.state === "running" ? stopContainer(c.name) : startContainer(c.name),
  ),
);

screen.key(
  ["r"],
  withFocusedContainer((c) => {
    if (c.state === "running") restartContainer(c.name);
  }),
);

screen.key(["d"], () => {
  const f = screen.focused;
  if (f === containersBox) {
    const c = dataCache.containers[selectedContainerIndex];
    if (!c) return;
    confirmDelete(`Delete container ${c.name}?`, () => deleteContainer(c.name));
  } else if (f === imagesBox) {
    const img = dataCache.images[selectedImageIndex];
    if (!img) return;
    confirmDelete(`Delete image ${img.repo}:${img.tag}?`, () =>
      deleteImage(img.id),
    );
  } else if (f === volumesBox) {
    const vol = dataCache.volumes[selectedVolumeIndex];
    if (!vol) return;
    confirmDelete(`Delete volume ${vol.name}?`, () => deleteVolume(vol.name));
  }
});

/* ---------- In-shell logs & exec ---------- */
screen.key(
  ["l"],
  withFocusedContainer((c) => {
    currentTab = 0;
    updateTabHeader();
    showContainerLogs(c.name, "all");
    screen.render();
  }),
);

/* ---------- in-shell exec (replaces screen.spawn) ---------- */
/* ---------- in-shell exec (replaces screen.spawn) ---------- */
screen.key(
  ["e"],
  withFocusedContainer((c) => {
    if (c.state !== "running") {
      showNotification("Container must be running to exec", "red");
      return;
    }

    // 1. Stop all background activity
    if (containersInterval) {
      clearInterval(containersInterval);
      containersInterval = null;
    }
    if (miscInterval) {
      clearInterval(miscInterval);
      miscInterval = null;
    }
    stopLogStream();
    if (statsProcess) {
      try {
        statsProcess.kill();
      } catch (_) {}
      statsProcess = null;
    }

    // 2. Completely suspend the blessed interface
    screen.program.showCursor();
    screen.program.disableMouse();
    screen.program.clear();
    screen.program.normalBuffer();

    // Detach all input handling
    screen.program.input.pause();
    screen.program.output.write("\x1b[?1049l"); // Exit alternate screen
    screen.program.output.write("\x1b[?25h"); // Show cursor

    // Reset terminal to cooked mode
    if (process.stdin.setRawMode) {
      process.stdin.setRawMode(false);
    }

    // 3. Small delay to ensure terminal is ready
    setTimeout(() => {
      const shellCmd = isWindows
        ? `wsl docker exec -it ${c.name} sh -c "exec /bin/bash || exec /bin/sh"`
        : `docker exec -it ${c.name} sh -c "exec /bin/bash || exec /bin/sh"`;

      const child = spawn(shellCmd, [], {
        stdio: "inherit",
        shell: true,
        detached: false,
      });

      child.on("exit", () => {
        // Small delay before restoring
        setTimeout(async () => {
          // 4. Restore raw mode
          if (process.stdin.setRawMode) {
            process.stdin.setRawMode(true);
          }

          // 5. Restore blessed screen
          screen.program.output.write("\x1b[?1049h"); // Enter alternate screen
          screen.program.input.resume();
          screen.program.alternateBuffer();
          screen.program.enableMouse();
          screen.program.hideCursor();

          // Recreate the display
          screen.alloc();
          screen.realloc();

          // Re-focus
          containersBox.focus();
          updateTabHeader();

          // 6. Refresh all data
          await updateAll();

          // 7. Restart everything
          startStatsStream();

          containersInterval = setInterval(async () => {
            await updateContainers();
            if (currentTab === 1) updateStatsTab();
            screen.render();
          }, 3000);

          miscInterval = setInterval(async () => {
            await Promise.all([
              updateImages(),
              updateVolumes(),
              updateNetworks(),
            ]);
            screen.render();
          }, 15000);

          // Restart logs if needed
          const currentContainer = dataCache.containers[selectedContainerIndex];
          if (currentTab === 0 && currentContainer) {
            showContainerLogs(currentContainer.name, "100");
          }

          screen.render();
        }, 100);
      });
    }, 100);
  }),
);

screen.key(
  ["C-e"],
  withFocusedContainer((c) => {
    if (c.state !== "running") {
      showNotification("Container must be running to exec", "red");
      return;
    }
    const cmd = `${dockerCmd} exec -it ${c.name} sh -c "exec /bin/bash || exec /bin/sh"`;
    spawnNewWindow(cmd, `exec-${c.name}`);
  }),
);

/* ---------- Misc ---------- */
screen.key(["a"], () => {
  logsAutoScroll = !logsAutoScroll;
  showNotification(
    `Auto-scroll: ${logsAutoScroll ? "ON" : "OFF"}`,
    logsAutoScroll ? "green" : "yellow",
  );
});

screen.key(["pageup"], () => {
  logsAutoScroll = false;
  contentBox.scroll(-10);
  screen.render();
});

screen.key(["pagedown"], () => {
  contentBox.scroll(10);
  screen.render();
});

// The list handlers for image/volume/network lists were already redundant/incomplete
// and are covered by the generic 'select item' handlers below. Removing the duplicates
// simplifies the code, but keeping the 'select item' handlers for correct index tracking.

// The 'd' key handler was duplicated, keeping the second, more comprehensive one.

/* ---------- Helper for confirmation dialog ---------- */
function confirmDelete(prompt, onConfirm) {
  const dialog = blessed.question({
    parent: screen,
    top: "center",
    left: "center",
    width: 50,
    height: 7,
    border: { type: "line" },
    style: { border: { fg: "red" }, fg: "white", bg: "black" },
  });

  dialog.ask(prompt, (err, value) => {
    if (value) onConfirm();
    screen.render();
  });
}

async function deleteImage(imageId) {
  try {
    await execPromise(`${dockerCmd} rmi -f ${imageId}`, { timeout: 30000 });
    showNotification(`Deleted image ${imageId}`, "yellow");
    await updateImages();
  } catch (err) {
    showNotification(`Failed to delete image: ${err.message}`, "red");
  }
}

async function deleteVolume(volumeName) {
  try {
    await execPromise(`${dockerCmd} volume rm -f ${volumeName}`, {
      timeout: 30000,
    });
    showNotification(`Deleted volume ${volumeName}`, "magenta");
    await updateVolumes();
  } catch (err) {
    showNotification(`Failed to delete volume: ${err.message}`, "red");
  }
}

// ==================== CLEANUP ====================

function cleanup() {
  stopLogStream();
  if (statsProcess) {
    statsProcess.kill();
    statsProcess = null;
  }
  if (containersInterval) clearInterval(containersInterval);
  if (miscInterval) clearInterval(miscInterval);
}

process.on("SIGINT", () => {
  cleanup();
  process.exit(0);
});

process.on("SIGTERM", () => {
  cleanup();
  process.exit(0);
});

// ==================== STARTUP ====================

containersBox.focus();
updateTabHeader();
screen.render();

(async () => {
  try {
    await execPromise(`${dockerCmd} --version`, { timeout: 5000 });

    await updateAll();

    /* keep our index in sync with the list’s cursor and handle log updates */
    containersBox.on("select item", async () => {
      selectedContainerIndex = containersBox.selected;
      const container = dataCache.containers[selectedContainerIndex];
      if (currentTab === 0 && container) {
        showContainerLogs(container.name, "100"); // Restart logs on selection change
      } else {
        // Update the display for other tabs immediately
        await updateCurrentTab();
      }
      updateHelpBar();
      screen.render();
    });

    // Remaining lists for index tracking (no need for tab updates)
    imagesBox.on("select item", () => {
      selectedImageIndex = imagesBox.selected;
      screen.render();
    });
    volumesBox.on("select item", () => {
      selectedVolumeIndex = volumesBox.selected;
      screen.render();
    });
    networksBox.on("select item", () => {
      selectedNetworkIndex = networksBox.selected;
      screen.render();
    });

    startStatsStream();

    // Start logs for first container (must be done after list handlers are set)
    if (dataCache.containers.length > 0) {
      showContainerLogs(dataCache.containers[0].name, "100");
    }

    // 1. Container/Stats Update Interval (3 seconds) - Correctly assigned to global variable
    containersInterval = setInterval(async () => {
      await updateContainers();
      if (currentTab === 1) updateStatsTab(); // Only update stats tab if visible
      screen.render();
    }, 3000);

    // 2. Misc Update Interval (15 seconds) - Correctly assigned to global variable
    miscInterval = setInterval(async () => {
      await Promise.all([updateImages(), updateVolumes(), updateNetworks()]);
      screen.render();
    }, 15000);

    // Removed the duplicate interval calls from the original file
  } catch (error) {
    contentBox.setContent(
      `{red-fg}Docker not accessible: ${error.message}{/red-fg}\n\nMake sure Docker is running.`,
    );
    screen.render();
  }
})();
