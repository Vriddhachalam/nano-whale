import { $ } from "bun";
import { cpSync, existsSync, mkdirSync, rmSync } from "fs";
import { join } from "path";

const version = "v1.0.0";
const platforms = [
  { target: "bun-windows-x64", ext: ".exe", name: "windows-x64" },
  { target: "bun-linux-x64", ext: "", name: "linux-x64" },
  { target: "bun-darwin-x64", ext: "", name: "macos-x64" },
  { target: "bun-darwin-arm64", ext: "", name: "macos-arm64" },
];

// Clean up old artifacts
console.log("🧹 Cleaning...");
const toClean = ["widgets", "lib", "dist", "releases"];
for (const dir of toClean) {
  if (existsSync(dir)) rmSync(dir, { recursive: true });
}

// Create releases directory
mkdirSync("releases", { recursive: true });

// Build for each platform
for (const platform of platforms) {
  console.log(`\n🔨 Building for ${platform.name}...`);
  const exeName = `nano-whale${platform.ext}`;
  
  await $`bun build --compile --target=${platform.target} ./nano_whale.js --outfile ${exeName}`;
  
  // Create distribution folder
  const distDir = `dist/${platform.name}`;
  mkdirSync(distDir, { recursive: true });
  mkdirSync(`${distDir}/node_modules`, { recursive: true });
  
  // Copy exe
  cpSync(exeName, `${distDir}/nano-whale${platform.ext}`);
  
  // Copy neo-blessed
  if (existsSync("node_modules/neo-blessed")) {
    cpSync(
      "node_modules/neo-blessed",
      `${distDir}/node_modules/neo-blessed`,
      { recursive: true }
    );
  }
  
  // Copy to releases folder
  const releaseDir = `releases/${platform.name}`;
  cpSync(distDir, releaseDir, { recursive: true });
  
  // Clean up
  rmSync(exeName);
}

console.log("\n✅ All builds complete!");
console.log("📦 Release packages in ./releases/");