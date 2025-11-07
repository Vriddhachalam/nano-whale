# 🐳 Nano Whale: Your Ultra-Light Docker Alternative for Windows
<p align="center">
  <img src="./img/nano_whale_w_bg.png" alt="Nano Whale logo" >
</p>


**STOP!** Before you go any further... are you tired of the lag, the CPU spikes, and the general bulk of Docker Desktop?

Meet **Nano Whale**! It's the lean, mean, resource-friendly alternative built for speed and simplicity. We said "see ya later" to heavy installs and complicated dependencies. By riding the power of **WSL 2** and being whipped up entirely with **standard Python libraries** (we mean **ZERO external dependencies)**, Nano Whale gives you a streamlined, no-fuss GUI to manage your containers, images, and volumes without breaking a sweat—or your computer's performance!



## ✨ **Features**

* Ultra-Lightweight: Forget the memory hogs. Minimal memory and CPU footprint compared to Docker Desktop.

* Pure Python & Zero Dependencies: Built entirely with standard, built-in Python libraries (like tkinter, subprocess, os)—no complex external packages or pip install requirements needed!

* WSL 2 Integration: Seamlessly manages the Docker Engine running directly within your Windows Subsystem for Linux (WSL 2) distribution.

* Single Executable: Exported as a portable .exe file for instant, clean use.

* Simple GUI: An intuitive graphical interface to view and manage your containers, images, and volumes.


## 🚀 Get Whale-ing: The Setup


### ⚠️ First Rule of Nano Whale Club: Uninstall Docker Desktop

Nano Whale is the future, which means we need to clear out the past! For a conflict-free and resource-optimized environment, you must first uninstall any existing installation of Docker Desktop.

Here’s the quick-and-dirty method:

* Open Windows **Settings**.

* Head to **Apps** (or **Installed Apps**).

* Find and click **Docker Desktop**.

* Hit that **Uninstall** button!



## 📥 Installation (The Smooth Way)

* Grab the latest **Nano_Whale.exe** from your project's [HERE](https://drive.google.com/file/d/1ZuKXWoyZovPs81luZN97Dscnve3wK5S7/view?usp=sharing).

* Run the executable **as Administrator (this is important!)**. Right-click and select **Run as administrator**. This is needed for the initial setup of WSL and the Docker Engine.

* The app will handle the rest, making sure WSL 2 and the Docker Engine are prepped and ready to go.

* Click **Uninstall**.




## 🔨 Exporting the Executable (Developer Instructions)

```bash
pyinstaller --onefile --noconsole --icon=nano_whale.ico main.py
```
The final **Nano_Whale.exe** will be located in the newly created /dist folder.

<p align="center">
  <img src="./img/face.png" alt="screens" width="738">
</p>
<p align="center">
  <img src="./img/images.png" alt="screens" width="738">
</p>
<p align="center">
  <img src="./img/logs.png" alt="screens" width="738">
</p>
<p align="center">
  <img src="./img/terminal.png" alt="screens" width="738">
</p>
