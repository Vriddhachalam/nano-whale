const path = require('path');
const Module = require('module');

// Module resolution patch for compiled executable
const isCompiled = !process.execPath.includes('bun') && (
  process.execPath.includes('nano-whale') || process.execPath.endsWith('.exe')
);

if (isCompiled) {
  const exeDir = path.dirname(process.execPath);
  const originalResolve = Module._resolveFilename;
  
  Module._resolveFilename = function(request, parent, isMain) {
    if (request.startsWith('./widgets') || request.startsWith('./events') || request.startsWith('../events')) {
      const neoBlessed = path.join(exeDir, 'node_modules', 'neo-blessed', 'lib');
      const resolved = path.join(neoBlessed, request.replace(/^\.\.?\//, ''));
      try { return originalResolve.call(this, resolved, parent, isMain); } catch (_) {}
    }
    if (!request.startsWith('.') && !request.startsWith('/')) {
      try {
        return originalResolve.call(this, path.join(exeDir, 'node_modules', request), parent, isMain);
      } catch (_) {}
    }
    return originalResolve.call(this, request, parent, isMain);
  };
}

const blessed = require('neo-blessed');
const { exec, spawn, execSync } = require("child_process");
const util = require("util");
const os = require("os");
const execPromise = util.promisify(exec);

const isWindows = os.platform() === "win32";
const dockerCmd = isWindows ? "wsl docker" : "docker";

// ==================== STATE ====================
const state = {
  containers: [],
  images: [],
  volumes: [],
  networks: [],
  stats: {},
  env: {},
  config: {},
  top: {},
  cpuHistory: {},
  memHistory: {},
  markedContainers: new Set(),
  markedImages: new Set(),
  markedVolumes: new Set(),
  selectedContainerIndex: 0,
  selectedImageIndex: 0,
  selectedVolumeIndex: 0,
  selectedNetworkIndex: 0,
  currentTab: 0,
  logsContent: "",
  logsAutoScroll: true,
  inFullscreenMode: false,
  statsProcess: null,
  logProcess: null,
  fullscreenChild: null,
  containersInterval: null,
  miscInterval: null,
};

const MAX_HISTORY = 80;
const TAB_NAMES = ["Logs", "Stats", "Env", "Config", "Top"];

// ==================== UI SETUP ====================
const screen = blessed.screen({
  smartCSR: true,
  title: "nano-whale",
  fullUnicode: true,
  fastCSR: true,
  mouse: true,
});

const originalRender = screen.render.bind(screen);
screen.render = () => !state.inFullscreenMode && originalRender();

const ui = {
  projectBox: blessed.box({
    top: 0, left: 0, width: "40%", height: 3,
    label: " [1]-Device ", border: { type: "line" },
    style: { border: { fg: "cyan" }, label: { fg: "cyan" } },
    content: os.hostname(),
  }),
  
  containersBox: blessed.list({
    top: 3, left: 0, width: "40%", height: "30%-3",
    label: " [2]-Containers ", border: { type: "line" },
    style: { border: { fg: "green" }, label: { fg: "green" }, selected: { bg: "blue", fg: "white", bold: true }, item: { fg: "white" } },
    scrollable: true, keys: true, vi: true, mouse: true, tags: true,
    scrollbar: { ch: "│", style: { fg: "green" } },
  }),
  
  imagesBox: blessed.list({
    top: "30%", left: 0, width: "40%", height: "25%",
    label: " [3]-Images ", border: { type: "line" },
    style: { border: { fg: "yellow" }, label: { fg: "yellow" }, selected: { bg: "yellow", fg: "black" } },
    scrollable: true, keys: true, vi: true, mouse: true, tags: true,
  }),
  
  volumesBox: blessed.list({
    top: "55%", left: 0, width: "40%", height: "22%",
    label: " [4]-Volumes ", border: { type: "line" },
    style: { border: { fg: "magenta" }, label: { fg: "magenta" }, selected: { bg: "magenta", fg: "black" } },
    scrollable: true, keys: true, vi: true, mouse: true, tags: true,
  }),
  
  networksBox: blessed.list({
    top: "77%", left: 0, width: "40%", height: "23%-1",
    label: " [5]-Networks ", border: { type: "line" },
    style: { border: { fg: "blue" }, label: { fg: "blue" }, selected: { bg: "blue", fg: "white" } },
    scrollable: true, keys: true, vi: true, mouse: true, tags: true,
  }),
  
  tabHeader: blessed.box({
    top: 0, left: "40%", width: "60%", height: 3,
    border: { type: "line" }, style: { border: { fg: "white" } },
    tags: true, mouse: true,
  }),
  
  contentBox: blessed.box({
    top: 3, left: "40%", width: "60%", height: "100%-4",
    border: { type: "line" }, style: { border: { fg: "cyan" }, label: { fg: "cyan" } },
    scrollable: true, keys: true, vi: true, mouse: true, tags: true,
    scrollbar: { ch: "│", style: { fg: "cyan" } },
  }),
  
  helpBar: blessed.box({
    bottom: 0, left: 0, width: "100%", height: 1,
    tags: true, style: { fg: "white", bg: "blue" }, mouse: true,
  }),
};

Object.values(ui).forEach(el => screen.append(el));

// Tab Header Click Handler
ui.tabHeader.on('click', async (data) => {
  if (state.inFullscreenMode) return;
  const clickX = data.x - ui.tabHeader.aleft;
  let offsetX = 1; // Start after border
  
  for (let i = 0; i < TAB_NAMES.length; i++) {
    const tabWidth = TAB_NAMES[i].length + 2; // " Name "
    const sepWidth = (i < TAB_NAMES.length - 1) ? 1 : 0; // "-" or ""
    const segmentWidth = tabWidth + sepWidth;
    
    if (clickX >= offsetX && clickX < offsetX + segmentWidth) {
      if (state.currentTab !== i) {
        state.currentTab = i;
        updateTabHeader();
        await updateCurrentTab();
        screen.render();
      }
      return;
    }
    offsetX += segmentWidth;
  }
});

// ==================== DOCKER API ====================
async function dockerExec(cmd, timeout = 5000) {
  try {
    const { stdout } = await execPromise(`${dockerCmd} ${cmd}`, { timeout });
    return stdout.trim();
  } catch (error) {
    return null;
  }
}

async function getContainers() {
  const out = await dockerExec('ps -a --format "{{.Names}}|{{.Status}}|{{.ID}}|{{.Image}}|{{.Ports}}|{{.State}}"');
  if (out === null) return state.containers;
  if (!out) return [];
  return out.split("\n").filter(Boolean).map(line => {
    const [name, status, id, image, ports, st] = line.split("|");
    return { name, status, id: id?.substring(0, 12) || "N/A", image, ports: ports || "", state: st || "unknown" };
  });
}

async function getImages() {
  const out = await dockerExec('images --format "{{.Repository}}|{{.Tag}}|{{.Size}}|{{.ID}}"');
  if (out === null) return state.images;
  if (!out) return [];
  return out.split("\n").filter(Boolean).map(line => {
    const [repo, tag, size, id] = line.split("|");
    return { repo, tag, size, id: id?.substring(0, 12) || "N/A" };
  });
}

async function getVolumes() {
  const out = await dockerExec('volume ls --format "{{.Driver}}|{{.Name}}"');
  if (out === null) return state.volumes;
  if (!out) return [];
  return out.split("\n").filter(Boolean).map(line => {
    const [driver, name] = line.split("|");
    return { driver: driver || "local", name: name || "N/A" };
  });
}

async function getNetworks() {
  const out = await dockerExec('network ls --format "{{.Driver}}|{{.Name}}"');
  if (out === null) return state.networks;
  if (!out) return [];
  return out.split("\n").filter(Boolean).map(line => {
    const [driver, name] = line.split("|");
    return { driver: driver || "bridge", name: name || "N/A" };
  });
}

async function getContainerEnv(name) {
  const out = await dockerExec(`inspect --format "{{range .Config.Env}}{{println .}}{{end}}" ${name}`);
  return out ? out.split("\n").filter(Boolean) : [];
}

async function getContainerTop(name) {
  const out = await dockerExec(`top ${name}`);
  return out || "Container not running";
}

async function getContainerInspect(name) {
  const out = await dockerExec(`inspect ${name}`);
  try { return JSON.parse(out)[0]; } catch { return null; }
}

// ==================== CONTAINER ACTIONS ====================
async function startContainer(name) {
  await dockerExec(`start ${name}`, 30000);
  notify(`Started ${name}`, "green");
  await updateAll();
}

async function stopContainer(name) {
  await dockerExec(`stop ${name}`, 30000);
  notify(`Stopped ${name}`, "yellow");
  await updateAll();
}

async function restartContainer(name) {
  await dockerExec(`restart ${name}`, 60000);
  notify(`Restarted ${name}`, "green");
  await updateAll();
}

async function deleteContainer(name) {
  try {
    const result = await execPromise(`${dockerCmd} rm -f ${name}`, { timeout: 30000 });
    notify(`Deleted ${name}`, "red");
    await updateAll();
  } catch (error) {
    notify(`Failed to delete container: ${error.message}`, "red");
  }
}

async function deleteImage(id) {
  try {
    const result = await execPromise(`${dockerCmd} rmi -f ${id}`, { timeout: 30000 });
    notify(`Deleted image ${id}`, "yellow");
    await updateImages();
  } catch (error) {
    notify(`Failed to delete image: ${error.message}`, "red");
  }
}

async function deleteVolume(name) {
  try {
    const result = await execPromise(`${dockerCmd} volume rm -f ${name}`, { timeout: 30000 });
    notify(`Deleted volume ${name}`, "magenta");
    await updateVolumes();
  } catch (error) {
    notify(`Failed to delete volume: ${error.message}`, "red");
  }
}

async function deleteNetwork(name) {
  try {
    const result = await execPromise(`${dockerCmd} network rm ${name}`, { timeout: 5000 });
    notify(`Deleted network ${name}`, "yellow");
    await updateAll();
  } catch (error) {
    notify(`Failed to delete network: ${error.message}`, "red");
  }
}

// ==================== STATS STREAMING ====================
function startStatsStream() {
  if (state.statsProcess) try { state.statsProcess.kill(); } catch (_) {}
  
  const [cmd, ...args] = [...dockerCmd.split(" "), "stats", "--no-stream=false", "--format", "table {{.Name}}\t{{.CPUPerc}}\t{{.MemPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}\t{{.PIDs}}"];
  state.statsProcess = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"] });
  
  let buffer = "";
  state.statsProcess.stdout.on("data", chunk => {
    buffer += chunk.toString();
    const lines = buffer.split("\n");
    buffer = lines.pop();
    
    lines.forEach(line => {
      if (!line.trim() || line.startsWith("NAME")) return;
      const parts = line.split(/\s{2,}|\t/);
      if (parts.length < 7) return;
      
      const [name, cpuStr, memStr, memUsage, netIO, blockIO, pids] = parts;
      if (!name) return;
      
      const cpu = parseFloat(cpuStr?.replace("%", "")) || 0;
      const mem = parseFloat(memStr?.replace("%", "")) || 0;
      
      state.stats[name] = { cpu, mem, memUsage: memUsage || "N/A", netIO: netIO || "N/A", blockIO: blockIO || "N/A", pids: pids || "N/A" };
      
      if (!state.cpuHistory[name]) state.cpuHistory[name] = [];
      if (!state.memHistory[name]) state.memHistory[name] = [];
      
      state.cpuHistory[name].push(cpu);
      state.memHistory[name].push(mem);
      
      if (state.cpuHistory[name].length > MAX_HISTORY) state.cpuHistory[name].shift();
      if (state.memHistory[name].length > MAX_HISTORY) state.memHistory[name].shift();
    });
    
    if (!state.inFullscreenMode && state.currentTab === 1) updateStatsTab();
  });
  
  state.statsProcess.on("close", () => {
    setTimeout(() => {
      if (!state.inFullscreenMode && (!state.statsProcess || state.statsProcess.killed)) startStatsStream();
    }, 2000);
  });
}

// ==================== LOGS ====================
function showContainerLogs(name, tail = "10") {
  if (!name || state.inFullscreenMode) return;
  stopLogStream();
  
  state.logsContent = "";
  const [cmd, ...args] = [...dockerCmd.split(" "), "logs", "-f", "--tail", tail, name];
  state.logProcess = spawn(cmd, args, { stdio: ['ignore', 'pipe', 'pipe'] });
  
  const onData = data => {
    if (state.inFullscreenMode) return;
    state.logsContent += data.toString();
    if (state.logsContent.length > 100000) state.logsContent = state.logsContent.slice(-100000);
    if (state.currentTab === 0) {
      ui.contentBox.setContent(state.logsContent);
      if (state.logsAutoScroll) ui.contentBox.setScrollPerc(100);
      screen.render();
    }
  };
  
  state.logProcess.stdout.on("data", onData);
  state.logProcess.stderr.on("data", onData);
}

function stopLogStream() {
  if (state.logProcess) {
    try {
      if (state.logProcess.stdout) state.logProcess.stdout.destroy();
      if (state.logProcess.stderr) state.logProcess.stderr.destroy();
      state.logProcess.kill('SIGKILL');
    } catch (_) {}
    state.logProcess = null;
  }
}

// ==================== CHARTS ====================
function smoothChart(data, height = 12, width = 60, color = "cyan", label = "") {
  if (!data || data.length < 2) {
    return Array(height).fill(" ".repeat(width)).join("\n") + `\n{${color}-fg}        ${label} 0.00 % (waiting…){/${color}-fg}`;
  }
  
  const slice = data.slice(-width);
  const max = Math.max(...slice);
  const min = Math.min(...slice);
  const range = max - min || 1;
  
  const dots = [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]];
  const pxW = width * 2, pxH = height * 4;
  const canvas = Array.from({ length: pxH }, () => Array(pxW).fill(0));
  const y = v => Math.round(pxH - 1 - ((v - min) / range) * (pxH - 1));
  
  for (let i = 0; i < slice.length - 1; i++) {
    const x0 = Math.round((i / (slice.length - 1)) * (pxW - 1));
    const x1 = Math.round(((i + 1) / (slice.length - 1)) * (pxW - 1));
    const y0 = y(slice[i]), y1 = y(slice[i + 1]);
    const steps = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0)) * 2;
    
    for (let s = 0; s <= steps; s++) {
      const t = s / steps;
      const sx = Math.round(x0 + (x1 - x0) * t);
      const sy = Math.round(y0 + (y1 - y0) * t);
      for (let dy = 0; dy <= 1; dy++) {
        for (let dx = 0; dx <= 1; dx++) {
          const cx = sx + dx, cy = sy + dy;
          if (cx >= 0 && cx < pxW && cy >= 0 && cy < pxH) canvas[cy][cx] = 1;
        }
      }
    }
  }
  
  const rows = [];
  for (let row = 0; row < pxH; row += 4) {
    let line = "";
    for (let col = 0; col < pxW; col += 2) {
      let code = 0x2800;
      for (let dy = 0; dy < 4; dy++) {
        for (let dx = 0; dx < 2; dx++) {
          if (canvas[row + dy]?.[col + dx]) code |= dots[dy][dx];
        }
      }
      line += String.fromCharCode(code);
    }
    const val = max - (row / 4 / (height - 1)) * range;
    rows.push(`${val.toFixed(2).padStart(6)} │{${color}-fg}${line}{/${color}-fg}`);
  }
  
  rows.push("       └" + "─".repeat(width));
  const cur = slice[slice.length - 1];
  rows.push(`\n{${color}-fg}        ${label} ${cur.toFixed(2)} %  (${slice.length * 2}s){/${color}-fg}`);
  return rows.join("\n");
}

function humanBytes(n) {
  const units = ["B", "kB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(1)}${units[i]}`;
}

// ==================== UI UPDATES ====================
function updateTabHeader() {
  let header = "";
  TAB_NAMES.forEach((name, i) => {
    header += i === state.currentTab ? `{cyan-fg}{bold} ${name} {/bold}{/cyan-fg}` : `{gray-fg} ${name} {/gray-fg}`;
    if (i < TAB_NAMES.length - 1) header += "{white-fg}-{/white-fg}";
  });
  ui.tabHeader.setContent(header);
}

function updateHelpBar() {
  ui.helpBar.setContent("{bold}q{/}:Quit {bold}←→{/}:Tabs {bold}↑↓{/}:Nav {bold}s{/}:Start/Stop {bold}r{/}:Restart {bold}t{/}:Exec {bold}d{/}:Delete {bold}m{/}:Mark {bold}C-a{/}:SelectAll {bold}l{/}:Logs {bold}a{/}:AutoScroll {bold}F5{/}:Refresh");
}

function updateListIfChanged(list, newData, formatFn, indexRef) {
  if (!newData || newData.length === 0) {
    const def = ["{yellow-fg}No items{/yellow-fg}"];
    if (list.items.length !== 1 || list.items[0].content !== def[0]) {
      list.setItems(def);
      list.select(0);
      screen.render();
    }
    indexRef[0] = 0;
    return;
  }
  
  const newItems = newData.map(formatFn);
  const hasChanged = list.items.length !== newItems.length || list.items.some((item, i) => item.content !== newItems[i]);
  
  if (hasChanged) {
    const wasFocused = screen.focused === list;
    const cur = list.selected;
    list.setItems(newItems);
    const idx = Math.min(cur, newItems.length - 1);
    list.select(Math.max(0, idx));
    if (wasFocused) list.focus();
    screen.render();
    indexRef[0] = Math.max(0, idx);
  } else {
    indexRef[0] = list.selected;
  }
}

async function updateContainers() {
  try {
    state.containers = await getContainers();
    const fmt = c => {
      const st = state.stats[c.name] || { cpu: 0, mem: 0 };
      const running = c.state === "running";
      const paused = c.status.includes("Paused");
      let status = running ? (paused ? "{yellow-fg}paused{/yellow-fg}" : "{green-fg}running{/green-fg}") : "{red-fg}exited{/red-fg}";
      if (c.status.includes("healthy")) status = "{green-fg}running (healthy){/green-fg}";
      const mark = state.markedContainers.has(c.name) ? "{white-bg}{black-fg}[✓]{/black-fg}{/white-bg} " : "    ";
      const name = c.name.substring(0, 18).padEnd(18);
      const cpu = running ? `${st.cpu.toFixed(2)}%`.padStart(7) : "      -";
      const ports = c.ports?.substring(0, 12) || "";
      return `${mark}${status.padEnd(25)} {bold}${name}{/bold} ${cpu} {cyan-fg}${ports}{/cyan-fg}`;
    };
    updateListIfChanged(ui.containersBox, state.containers, fmt, [state.selectedContainerIndex]);
    state.selectedContainerIndex = ui.containersBox.selected;
    updateHelpBar();
  } catch (err) {
    ui.containersBox.setItems([`{red-fg}Error: ${err.message}{/red-fg}`]);
  }
}

async function updateImages(force = false) {
  try {
    const imgs = await getImages();
    if (!force && JSON.stringify(imgs) === JSON.stringify(state.images)) return;
    state.images = imgs;
    const fmt = img => {
      const mark = state.markedImages.has(img.id) ? "{white-bg}{black-fg}[✓]{/black-fg}{/white-bg} " : "    ";
      return `${mark}${img.repo.substring(0, 20).padEnd(20)} {yellow-fg}${img.tag.substring(0, 10).padEnd(10)}{/yellow-fg} ${img.size.padEnd(10)}`;
    };
    updateListIfChanged(ui.imagesBox, state.images, fmt, [state.selectedImageIndex]);
    state.selectedImageIndex = ui.imagesBox.selected;
  } catch { ui.imagesBox.setItems(["{red-fg}Error{/red-fg}"]); }
}

async function updateVolumes(force = false) {
  try {
    const vols = await getVolumes();
    if (!force && JSON.stringify(vols) === JSON.stringify(state.volumes)) return;
    state.volumes = vols;
    const fmt = v => {
      const mark = state.markedVolumes.has(v.name) ? "{white-bg}{black-fg}[✓]{/black-fg}{/white-bg} " : "    ";
      return `${mark}{magenta-fg}${v.driver.padEnd(8)}{/magenta-fg} ${v.name}`;
    };
    updateListIfChanged(ui.volumesBox, state.volumes, fmt, [state.selectedVolumeIndex]);
    state.selectedVolumeIndex = ui.volumesBox.selected;
  } catch { ui.volumesBox.setItems(["{red-fg}Error{/red-fg}"]); }
}

async function updateNetworks() {
  try {
    const nets = await getNetworks();
    if (JSON.stringify(nets) === JSON.stringify(state.networks)) return;
    state.networks = nets;
    const sys = ['bridge', 'host', 'none'];
    const fmt = n => sys.includes(n.name) ? `{gray-fg}${n.driver.padEnd(8)} ${n.name} (system){/gray-fg}` : `{blue-fg}${n.driver.padEnd(8)}{/blue-fg} ${n.name}`;
    updateListIfChanged(ui.networksBox, state.networks, fmt, [state.selectedNetworkIndex]);
    state.selectedNetworkIndex = ui.networksBox.selected;
  } catch { ui.networksBox.setItems(["{red-fg}Error{/red-fg}"]); }
}

async function updateAll() {
  state.env = {};
  state.config = {};
  state.top = {};
  await Promise.all([updateContainers(), updateImages(), updateVolumes(), updateNetworks()]);
  await updateCurrentTab();
  screen.render();
}

// ==================== TAB CONTENT ====================
function updateLogsTab() {
  const c = state.containers[state.selectedContainerIndex];
  ui.contentBox.setContent(c ? (state.logsContent || "{gray-fg}No logs yet...{/gray-fg}") : "{yellow-fg}No container selected{/yellow-fg}");
  screen.render();
}

function updateStatsTab() {
  const c = state.containers[state.selectedContainerIndex];
  if (!c) {
    ui.contentBox.setContent("{yellow-fg}No container selected{/yellow-fg}");
    screen.render();
    return;
  }
  
  const st = state.stats[c.name] || {};
  const running = c.state === "running";
  
  if (!state.cpuHistory[c.name]) state.cpuHistory[c.name] = [0];
  if (!state.memHistory[c.name]) state.memHistory[c.name] = [0];
  
  let out = `{bold}{cyan-fg}Stats: ${c.name}{/cyan-fg}{/bold}\n{gray-fg}${"─".repeat(60)}{/gray-fg}\n\n`;
  
  if (!running) {
    out += "{gray-fg}Container is not running\nPress [s] to start{/gray-fg}\n";
  } else {
    out += smoothChart(state.cpuHistory[c.name], 12, 55, "cyan", "CPU:   ") + "\n\n";
    out += smoothChart(state.memHistory[c.name], 12, 55, "green", "Memory:") + "\n\n";
    
    const [rx, tx] = (st.netIO || "0B / 0B").split(" / ");
    const [read, write] = (st.blockIO || "0B / 0B").split(" / ");
    const parseBytes = s => parseFloat(s.match(/^([\d.]+)/)?.[1] || 0);
    
    out += `{bold}{yellow-fg}PIDs:{/yellow-fg}{/bold}     ${st.pids || "N/A"}\n`;
    out += `{bold}{blue-fg}Net RX:{/blue-fg}{/bold}   ${humanBytes(parseBytes(rx))}\n`;
    out += `{bold}{blue-fg}Net TX:{/blue-fg}{/bold}   ${humanBytes(parseBytes(tx))}\n`;
    out += `{bold}{magenta-fg}Disk R:{/magenta-fg}{/bold}   ${humanBytes(parseBytes(read))}\n`;
    out += `{bold}{magenta-fg}Disk W:{/magenta-fg}{/bold}   ${humanBytes(parseBytes(write))}\n`;
  }
  
  ui.contentBox.setContent(out);
  screen.render();
}

async function updateEnvTab() {
  const c = state.containers[state.selectedContainerIndex];
  if (!c) {
    ui.contentBox.setContent("{yellow-fg}No container selected{/yellow-fg}");
    return;
  }
  
  if (state.env[c.name]) {
    renderEnv(c.name, state.env[c.name]);
    return;
  }
  
  const envVars = await getContainerEnv(c.name);
  state.env[c.name] = envVars;
  renderEnv(c.name, envVars);
}

function renderEnv(name, envVars) {
  let content = `{bold}{cyan-fg}Environment Variables: ${name}{/cyan-fg}{/bold}\n{gray-fg}${"─".repeat(55)}{/gray-fg}\n\n`;
  if (envVars.length === 0) {
    content += "{yellow-fg}No environment variables found{/yellow-fg}\n";
  } else {
    envVars.forEach(env => {
      const eqIdx = env.indexOf("=");
      if (eqIdx > 0) {
        const key = env.substring(0, eqIdx);
        const val = env.substring(eqIdx + 1);
        content += `{bold}${key}{/bold}={green-fg}${val}{/green-fg}\n`;
      } else {
        content += `${env}\n`;
      }
    });
  }
  ui.contentBox.setContent(content);
  screen.render();
}

async function updateConfigTab() {
  const c = state.containers[state.selectedContainerIndex];
  if (!c) {
    ui.contentBox.setContent("{yellow-fg}No container selected{/yellow-fg}");
    return;
  }
  
  if (state.config[c.name]) {
    renderConfig(c.name, state.config[c.name]);
    return;
  }
  
  const inspect = await getContainerInspect(c.name);
  state.config[c.name] = inspect;
  renderConfig(c.name, inspect);
}

function renderConfig(name, inspect) {
  let content = `{bold}{cyan-fg}Configuration: ${name}{/cyan-fg}{/bold}\n{gray-fg}${"─".repeat(55)}{/gray-fg}\n\n`;
  if (!inspect) {
    content += "{red-fg}Failed to get container configuration{/red-fg}\n";
  } else {
    content += `{bold}ID:{/bold} ${inspect.Id?.substring(0, 12) || "N/A"}\n`;
    content += `{bold}Created:{/bold} ${inspect.Created || "N/A"}\n`;
    content += `{bold}Image:{/bold} ${inspect.Config?.Image || "N/A"}\n`;
    content += `{bold}Entrypoint:{/bold} ${JSON.stringify(inspect.Config?.Entrypoint) || "N/A"}\n`;
    content += `{bold}Cmd:{/bold} ${JSON.stringify(inspect.Config?.Cmd) || "N/A"}\n`;
    content += `{bold}WorkingDir:{/bold} ${inspect.Config?.WorkingDir || "/"}\n\n`;
    
    content += `{bold}{yellow-fg}Network Settings:{/yellow-fg}{/bold}\n`;
    const networks = inspect.NetworkSettings?.Networks || {};
    for (const [netName, netConfig] of Object.entries(networks)) {
      content += `  {bold}${netName}:{/bold}\n`;
      content += `    IP: ${netConfig.IPAddress || "N/A"}\n`;
      content += `    Gateway: ${netConfig.Gateway || "N/A"}\n`;
      content += `    MAC: ${netConfig.MacAddress || "N/A"}\n`;
    }
    content += "\n";
    
    content += `{bold}{green-fg}Port Bindings:{/green-fg}{/bold}\n`;
    const ports = inspect.NetworkSettings?.Ports || {};
    if (Object.keys(ports).length === 0) {
      content += "  {gray-fg}No ports exposed{/gray-fg}\n";
    } else {
      for (const [containerPort, hostBindings] of Object.entries(ports)) {
        if (hostBindings) {
          hostBindings.forEach(binding => {
            content += `  {cyan-fg}${binding.HostIp || "0.0.0.0"}:${binding.HostPort}{/cyan-fg} -> ${containerPort}\n`;
          });
        } else {
          content += `  ${containerPort} (not bound)\n`;
        }
      }
    }
    content += "\n";
    
    content += `{bold}{magenta-fg}Mounts:{/magenta-fg}{/bold}\n`;
    const mounts = inspect.Mounts || [];
    if (mounts.length === 0) {
      content += "  {gray-fg}No mounts{/gray-fg}\n";
    } else {
      mounts.forEach(mount => {
        content += `  ${mount.Type}: ${mount.Source || "N/A"}\n`;
        content += `    -> ${mount.Destination}\n`;
      });
    }
    content += "\n";
    
    content += `{bold}{red-fg}Resource Limits:{/red-fg}{/bold}\n`;
    const hostConfig = inspect.HostConfig || {};
    content += `  CPU Shares: ${hostConfig.CpuShares || "default"}\n`;
    content += `  Memory Limit: ${hostConfig.Memory ? (hostConfig.Memory / 1024 / 1024).toFixed(0) + "MB" : "unlimited"}\n`;
    content += `  Restart Policy: ${hostConfig.RestartPolicy?.Name || "no"}\n`;
  }
  ui.contentBox.setContent(content);
  screen.render();
}

async function updateTopTab() {
  const c = state.containers[state.selectedContainerIndex];
  if (!c) {
    ui.contentBox.setContent("{yellow-fg}No container selected{/yellow-fg}");
    return;
  }
  
  if (state.top[c.name]) {
    renderTop(c.name, state.top[c.name]);
    return;
  }
  
  const topInfo = c.state === "running" ? await getContainerTop(c.name) : "Container is not running";
  state.top[c.name] = topInfo;
  renderTop(c.name, topInfo);
}

function renderTop(name, topInfo) {
  let content = `{bold}{cyan-fg}Top Processes: ${name}{/cyan-fg}{/bold}\n{gray-fg}${"─".repeat(55)}{/gray-fg}\n\n`;
  const c = state.containers[state.selectedContainerIndex];
  content += c?.state === "running" ? `{green-fg}${topInfo}{/green-fg}\n\n` : "{gray-fg}Container is not running{/gray-fg}\n\n";
  ui.contentBox.setContent(content);
  screen.render();
}

async function updateCurrentTab() {
  const c = state.containers[state.selectedContainerIndex];
  
  if (!c && state.containers.length === 0) {
    ui.contentBox.setContent("{yellow-fg}No containers available. Start Docker or create one.{/yellow-fg}");
    screen.render();
    return;
  }
  
  if (!c) return;
  
  if (state.currentTab === 0 && (!state.logProcess || !state.logProcess.spawnargs?.includes(c.name))) {
    showContainerLogs(c.name, "100");
    return;
  }
  
  if (state.currentTab !== 0) stopLogStream();
  
  const tabs = [updateLogsTab, updateStatsTab, updateEnvTab, updateConfigTab, updateTopTab];
  await tabs[state.currentTab]();
  screen.render();
}

// ==================== UTILITIES ====================
function notify(msg, color = "green") {
  const box = blessed.box({
    top: "center", left: "center",
    width: Math.min(msg.length + 6, 60), height: 3,
    content: ` ${msg} `, border: { type: "line" },
    style: { border: { fg: color }, fg: color, bg: "black" },
  });
  screen.append(box);
  screen.render();
  setTimeout(() => { screen.remove(box); screen.render(); }, 2000);
}

function confirmDelete(prompt, onConfirm) {
  const dialog = blessed.question({
    parent: screen, top: "center", left: "center",
    width: 50, height: 7, border: { type: "line" },
    style: { border: { fg: "red" }, fg: "white", bg: "black" },
  });
  dialog.ask(prompt, (err, value) => {
    if (value) onConfirm();
    screen.render();
  });
}

function cleanup() {
  if (state.logProcess) try { state.logProcess.kill('SIGKILL'); } catch (_) {}
  if (state.statsProcess) try { state.statsProcess.kill('SIGKILL'); } catch (_) {}
  if (state.fullscreenChild) {
    try { process.kill(-state.fullscreenChild.pid, 'SIGKILL'); } catch (_) {
      try { state.fullscreenChild.kill('SIGKILL'); } catch (_) {}
    }
  }
  if (state.containersInterval) clearInterval(state.containersInterval);
  if (state.miscInterval) clearInterval(state.miscInterval);
}

// ==================== KEYBOARD HANDLERS ====================
screen.key(["q", "C-c"], () => {
  if (state.inFullscreenMode) return;
  cleanup();
  process.exit(0);
});

screen.key(["F5"], () => !state.inFullscreenMode && updateAll());

screen.key(["right"], async () => {
  if (state.inFullscreenMode) return;
  state.currentTab = (state.currentTab + 1) % TAB_NAMES.length;
  updateTabHeader();
  await updateCurrentTab();
});

screen.key(["left"], async () => {
  if (state.inFullscreenMode) return;
  state.currentTab = (state.currentTab - 1 + TAB_NAMES.length) % TAB_NAMES.length;
  updateTabHeader();
  await updateCurrentTab();
});

screen.key(["2"], () => !state.inFullscreenMode && ui.containersBox.focus() && screen.render());
screen.key(["3"], () => !state.inFullscreenMode && ui.imagesBox.focus() && screen.render());
screen.key(["4"], () => !state.inFullscreenMode && ui.volumesBox.focus() && screen.render());
screen.key(["5"], () => !state.inFullscreenMode && ui.networksBox.focus() && screen.render());

// Mark/unmark items
screen.key(["m"], async () => {
  if (state.inFullscreenMode) return;
  const f = screen.focused;
  
  if (f === ui.containersBox) {
    const c = state.containers[state.selectedContainerIndex];
    if (c) {
      state.markedContainers.has(c.name) ? state.markedContainers.delete(c.name) : state.markedContainers.add(c.name);
      await updateContainers();
    }
  } else if (f === ui.imagesBox) {
    const img = state.images[state.selectedImageIndex];
    if (img) {
      state.markedImages.has(img.id) ? state.markedImages.delete(img.id) : state.markedImages.add(img.id);
      await updateImages(true);
    }
  } else if (f === ui.volumesBox) {
    const vol = state.volumes[state.selectedVolumeIndex];
    if (vol) {
      state.markedVolumes.has(vol.name) ? state.markedVolumes.delete(vol.name) : state.markedVolumes.add(vol.name);
      await updateVolumes(true);
    }
  }
  screen.render();
});

// Select all
screen.key(["C-a"], async () => {
  if (state.inFullscreenMode) return;
  const f = screen.focused;
  
  if (f === ui.containersBox) {
    if (state.markedContainers.size === state.containers.length) {
      state.markedContainers.clear();
      notify("Deselected all containers", "yellow");
    } else {
      state.containers.forEach(c => state.markedContainers.add(c.name));
      notify(`Selected ${state.markedContainers.size} containers`, "green");
    }
    await updateContainers();
  } else if (f === ui.imagesBox) {
    if (state.markedImages.size === state.images.length) {
      state.markedImages.clear();
      notify("Deselected all images", "yellow");
    } else {
      state.images.forEach(img => state.markedImages.add(img.id));
      notify(`Selected ${state.markedImages.size} images`, "green");
    }
    await updateImages(true);
  } else if (f === ui.volumesBox) {
    if (state.markedVolumes.size === state.volumes.length) {
      state.markedVolumes.clear();
      notify("Deselected all volumes", "yellow");
    } else {
      state.volumes.forEach(v => state.markedVolumes.add(v.name));
      notify(`Selected ${state.markedVolumes.size} volumes`, "green");
    }
    await updateVolumes(true);
  }
  screen.render();
});

// Container actions
screen.key(["s"], async () => {
  if (state.inFullscreenMode || screen.focused !== ui.containersBox) return;
  
  if (state.markedContainers.size > 0) {
    const containers = state.containers.filter(c => state.markedContainers.has(c.name));
    const toStart = containers.filter(c => c.state !== "running");
    const toStop = containers.filter(c => c.state === "running");
    
    if (toStart.length > 0) {
      notify(`Starting ${toStart.length} container(s)...`, "green");
      for (const c of toStart) await startContainer(c.name);
    }
    if (toStop.length > 0) {
      notify(`Stopping ${toStop.length} container(s)...`, "yellow");
      for (const c of toStop) await stopContainer(c.name);
    }
    state.markedContainers.clear();
    await updateContainers();
  } else {
    const c = state.containers[state.selectedContainerIndex];
    if (c) c.state === "running" ? await stopContainer(c.name) : await startContainer(c.name);
  }
});

screen.key(["r"], async () => {
  if (state.inFullscreenMode || screen.focused !== ui.containersBox) return;
  
  if (state.markedContainers.size > 0) {
    const containers = state.containers.filter(c => state.markedContainers.has(c.name) && c.state === "running");
    if (containers.length > 0) {
      notify(`Restarting ${containers.length} container(s)...`, "blue");
      for (const c of containers) await restartContainer(c.name);
    } else {
      notify("No running containers selected", "yellow");
    }
    state.markedContainers.clear();
    await updateContainers();
  } else {
    const c = state.containers[state.selectedContainerIndex];
    if (c && c.state === "running") await restartContainer(c.name);
  }
});

// Delete
screen.key(["d"], async () => {
  if (state.inFullscreenMode) return;
  const f = screen.focused;
  
  if (f === ui.containersBox) {
    if (state.markedContainers.size > 0) {
      confirmDelete(`Delete ${state.markedContainers.size} container(s)?`, async () => {
        for (const name of state.markedContainers) await deleteContainer(name);
        state.markedContainers.clear();
        await updateContainers();
      });
    } else {
      const c = state.containers[state.selectedContainerIndex];
      if (c) confirmDelete(`Delete container ${c.name}?`, () => deleteContainer(c.name));
    }
  } else if (f === ui.imagesBox) {
    if (state.markedImages.size > 0) {
      confirmDelete(`Delete ${state.markedImages.size} image(s)?`, async () => {
        for (const id of state.markedImages) await deleteImage(id);
        state.markedImages.clear();
        await updateImages();
      });
    } else {
      const img = state.images[state.selectedImageIndex];
      if (img) confirmDelete(`Delete image ${img.repo}:${img.tag}?`, () => deleteImage(img.id));
    }
  } else if (f === ui.volumesBox) {
    if (state.markedVolumes.size > 0) {
      confirmDelete(`Delete ${state.markedVolumes.size} volume(s)?`, async () => {
        for (const name of state.markedVolumes) await deleteVolume(name);
        state.markedVolumes.clear();
        await updateVolumes();
      });
    } else {
      const vol = state.volumes[state.selectedVolumeIndex];
      if (vol) confirmDelete(`Delete volume ${vol.name}?`, () => deleteVolume(vol.name));
    }
  } else if (f === ui.networksBox) {
    const net = state.networks[state.selectedNetworkIndex];
    if (net) {
      if (['bridge', 'host', 'none'].includes(net.name)) {
        notify(`Cannot delete '${net.name}' - system network`, "yellow");
      } else {
        confirmDelete(`Delete network ${net.name}?`, () => deleteNetwork(net.name));
      }
    }
  }
});

// Exec into container (in-shell)
screen.key(["t"], () => {
  if (state.inFullscreenMode || screen.focused !== ui.containersBox) return;
  const c = state.containers[state.selectedContainerIndex];
  if (!c || c.state !== "running") {
    notify("Container must be running", "red");
    return;
  }
  
  state.inFullscreenMode = true;
  if (state.containersInterval) clearInterval(state.containersInterval);
  if (state.miscInterval) clearInterval(state.miscInterval);
  stopLogStream();
  if (state.statsProcess) try { state.statsProcess.kill(); } catch (_) {}
  
  screen.lockKeys = true;
  screen.program.showCursor();
  screen.program.disableMouse();
  screen.program.clear();
  screen.program.normalBuffer();
  screen.program.input.pause();
  screen.program.output.write("\x1b[?1049l\x1b[?25h");
  if (process.stdin.setRawMode) process.stdin.setRawMode(false);
  
  setTimeout(() => {
    const shellCmd = isWindows ? `wsl docker exec -it ${c.name} sh -c "exec /bin/bash || exec /bin/sh"` : `docker exec -it ${c.name} sh -c "exec /bin/bash || exec /bin/sh"`;
    process.stdout.write('\r\n🐳 Entering shell in ' + c.name + '...\r\n📋 Press Ctrl+D to return\r\n\r\n');
    
    const child = spawn(shellCmd, [], { stdio: "inherit", shell: true });
    state.fullscreenChild = child;
    
    child.on("exit", () => {
      state.fullscreenChild = null;
      setTimeout(async () => {
        if (process.stdin.setRawMode) process.stdin.setRawMode(true);
        state.inFullscreenMode = false;
        screen.lockKeys = false;
        screen.program.output.write("\x1b[?1049h");
        screen.program.input.resume();
        screen.program.alternateBuffer();
        screen.program.enableMouse();
        screen.program.hideCursor();
        screen.alloc();
        screen.realloc();
        ui.containersBox.focus();
        updateTabHeader();
        await updateAll();
        startStatsStream();
        state.containersInterval = setInterval(async () => {
          await updateContainers();
          if (state.currentTab === 1) updateStatsTab();
          screen.render();
        }, 3000);
        state.miscInterval = setInterval(async () => {
          await Promise.all([updateImages(), updateVolumes(), updateNetworks()]);
          screen.render();
        }, 15000);
        const cur = state.containers[state.selectedContainerIndex];
        if (state.currentTab === 0 && cur) showContainerLogs(cur.name, "100");
        screen.render();
      }, 100);
    });
  }, 100);
});

// View logs (in-shell)
screen.key(["l"], () => {
  if (state.inFullscreenMode || screen.focused !== ui.containersBox) return;
  const c = state.containers[state.selectedContainerIndex];
  if (!c || c.state !== "running") {
    notify("Container must be running", "red");
    return;
  }
  
  state.inFullscreenMode = true;
  if (state.containersInterval) clearInterval(state.containersInterval);
  if (state.miscInterval) clearInterval(state.miscInterval);
  stopLogStream();
  if (state.statsProcess) try { state.statsProcess.kill(); } catch (_) {}
  
  screen.lockKeys = true;
  screen.program.showCursor();
  screen.program.disableMouse();
  screen.program.clear();
  screen.program.normalBuffer();
  screen.program.input.pause();
  screen.program.output.write("\x1b[?1049l\x1b[?25h");
  if (process.stdin.setRawMode) process.stdin.setRawMode(false);
  
  setTimeout(() => {
    const cmdParts = isWindows ? ['wsl', 'docker', 'logs', '-f', c.name] : ['docker', 'logs', '-f', c.name];
    if (process.stdin.setRawMode) process.stdin.setRawMode(true);
    process.stdin.resume();
    
    const child = spawn(cmdParts[0], cmdParts.slice(1), { stdio: ["ignore", "inherit", "inherit"], detached: !isWindows });
    state.fullscreenChild = child;
    
    const onData = key => {
      if (key[0] === 0x04) {
        try { process.kill(-child.pid, 'SIGKILL'); } catch (_) { child.kill('SIGKILL'); }
      }
    };
    process.stdin.on('data', onData);
    
    child.on("exit", () => {
      state.fullscreenChild = null;
      process.stdin.removeListener('data', onData);
      setTimeout(async () => {
        if (process.stdin.setRawMode) process.stdin.setRawMode(true);
        state.inFullscreenMode = false;
        screen.lockKeys = false;
        screen.program.output.write("\x1b[?1049h");
        screen.program.input.resume();
        screen.program.alternateBuffer();
        screen.program.enableMouse();
        screen.program.hideCursor();
        screen.alloc();
        screen.realloc();
        ui.containersBox.focus();
        updateTabHeader();
        await updateAll();
        startStatsStream();
        state.containersInterval = setInterval(async () => {
          await updateContainers();
          if (state.currentTab === 1) updateStatsTab();
          screen.render();
        }, 3000);
        state.miscInterval = setInterval(async () => {
          await Promise.all([updateImages(), updateVolumes(), updateNetworks()]);
          screen.render();
        }, 15000);
        const cur = state.containers[state.selectedContainerIndex];
        if (state.currentTab === 0 && cur) showContainerLogs(cur.name, "100");
        screen.render();
      }, 100);
    });
  }, 100);
});

screen.key(["a"], () => {
  state.logsAutoScroll = !state.logsAutoScroll;
  notify(`Auto-scroll: ${state.logsAutoScroll ? "ON" : "OFF"}`, state.logsAutoScroll ? "green" : "yellow");
});

screen.key(["pageup"], () => {
  state.logsAutoScroll = false;
  ui.contentBox.scroll(-10);
  screen.render();
});

screen.key(["pagedown"], () => {
  ui.contentBox.scroll(10);
  screen.render();
});

// New terminal windows for exec and logs
screen.key(["C-t"], () => {
  if (state.inFullscreenMode || screen.focused !== ui.containersBox) return;
  const c = state.containers[state.selectedContainerIndex];
  if (!c || c.state !== "running") {
    notify("Container must be running", "red");
    return;
  }
  
  const cmd = `${dockerCmd} exec -it ${c.name} sh -c "exec /bin/bash || exec /bin/sh"`;
  spawnNewWindow(cmd, `exec-${c.name}`);
});

screen.key(["C-l"], () => {
  if (state.inFullscreenMode || screen.focused !== ui.containersBox) return;
  const c = state.containers[state.selectedContainerIndex];
  if (!c || c.state !== "running") {
    notify("Container must be running", "red");
    return;
  }
  
  const cmd = `${dockerCmd} logs -f ${c.name}`;
  spawnNewWindow(cmd, `logs-${c.name}`);
});

function spawnNewWindow(cmd, label) {
  const plat = os.platform();
  
  if (plat === "win32") {
    // Try Windows Terminal first
    try {
      execSync("where wt", { stdio: "ignore" });
      exec(`wt new-tab --title "${label}" cmd /k ${cmd}`, (error) => {
        if (error) notify(`Failed to open Windows Terminal: ${error.message}`, "red");
      });
      notify(`Opened new tab in Windows Terminal`, "green");
      return;
    } catch (_) {}
    
    // Fallback to Git Bash
    try {
      execSync("where mintty", { stdio: "ignore" });
      const bashPath = process.env.SHELL || "C:\\Program Files\\Git\\bin\\bash.exe";
      exec(`mintty -t "${label}" -e ${bashPath} -c "${cmd}"`, (error) => {
        if (error) notify(`Failed to open Git Bash: ${error.message}`, "red");
      });
      notify(`Opened new Git Bash window`, "green");
      return;
    } catch (_) {}
    
    // Last resort: cmd.exe
    exec(`start cmd /k ${cmd}`, (error) => {
      if (error) notify(`Failed to open cmd: ${error.message}`, "red");
    });
    notify(`Opened new cmd window`, "green");
    return;
  }
  
  if (plat === "darwin") {
    exec(`osascript -e 'tell application "Terminal" to do script "${cmd}"'`, (error) => {
      if (error) notify(`Failed to open Terminal: ${error.message}`, "red");
    });
    notify(`Opened new Terminal window`, "green");
    return;
  }
  
  // Linux
  if (plat === "linux") {
    const candidates = [
      {
        bin: "x-terminal-emulator",
        args: ["-e", "bash", "-c", `${cmd}; exec bash`],
      },
      {
        bin: "gnome-terminal",
        args: ["--", "bash", "-c", `${cmd}; exec bash`],
      },
      {
        bin: "xterm",
        args: ["-T", label, "-e", `${cmd}; bash`],
      },
      {
        bin: "konsole",
        args: ["-e", "bash", "-c", `${cmd}; exec bash`],
      },
    ];

    for (const t of candidates) {
      try {
        execSync(`which ${t.bin}`, { stdio: "ignore" });

        // Spawn correctly with detached session
        spawn(t.bin, t.args, {
          detached: true,
          stdio: "ignore"
        });

        notify(`Opened new terminal window`, "green");
        return;
      } catch (_) {
        // Try next one
      }
    }
  }
  
  notify("No terminal found. Run manually: " + cmd, "yellow");
}

// ==================== STARTUP ====================
process.on("SIGINT", () => { cleanup(); process.exit(0); });
process.on("SIGTERM", () => { cleanup(); process.exit(0); });
process.on("exit", cleanup);

ui.containersBox.focus();
updateTabHeader();
updateHelpBar();
screen.render();

(async () => {
  try {
    await execPromise(`${dockerCmd} --version`, { timeout: 10000 });
    await updateAll();
    
    ui.containersBox.on("select item", async () => {
      state.selectedContainerIndex = ui.containersBox.selected;
      const c = state.containers[state.selectedContainerIndex];
      if (state.currentTab === 0 && c) {
        showContainerLogs(c.name, "100");
      } else {
        await updateCurrentTab();
      }
      updateHelpBar();
      screen.render();
    });
    
    ui.imagesBox.on("select item", () => {
      state.selectedImageIndex = ui.imagesBox.selected;
      screen.render();
    });
    
    ui.volumesBox.on("select item", () => {
      state.selectedVolumeIndex = ui.volumesBox.selected;
      screen.render();
    });
    
    ui.networksBox.on("select item", () => {
      state.selectedNetworkIndex = ui.networksBox.selected;
      screen.render();
    });
    
    startStatsStream();
    
    if (state.containers.length > 0) {
      showContainerLogs(state.containers[0].name, "100");
    }
    
    state.containersInterval = setInterval(async () => {
      await updateContainers();
      if (state.currentTab === 1) updateStatsTab();
      screen.render();
    }, 3000);
    
    state.miscInterval = setInterval(async () => {
      await Promise.all([updateImages(), updateVolumes(), updateNetworks()]);
      screen.render();
    }, 15000);
    
  } catch (error) {
    ui.contentBox.setContent(`{red-fg}Docker not accessible: ${error.message}{/red-fg}\n\nMake sure Docker is running.`);
    screen.render();
  }
})();