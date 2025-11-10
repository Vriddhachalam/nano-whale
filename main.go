// main.go (Fixed)
package main

import (
	"bufio"
	"context"
	"fmt"
	"os/exec"
	"strings"
	"sync"
	"time"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/data/binding"
	"fyne.io/fyne/v2/dialog"
	"fyne.io/fyne/v2/widget"
)

// Configuration
var dockerCmdPrefix = []string{"wsl", "docker"}

// ContainerInfo represents a Docker container
type ContainerInfo struct {
	ID     string
	Name   string
	Image  string
	Status string
}

// ImageInfo represents a Docker image
type ImageInfo struct {
	ID         string
	Repository string
	Tag        string
	Size       string
}

// VolumeInfo represents a Docker volume
type VolumeInfo struct {
	Name   string
	Driver string
}

// LogStreamer manages log streaming
type LogStreamer struct {
	containerID    string
	cmd            *exec.Cmd
	cancel         context.CancelFunc
	running        bool
	mu             sync.Mutex
	showTimestamps bool
	sinceTime      string
	untilTime      string
	// FIX: Add a reference to the widget to be updated
	textWidget *widget.Entry
}

// App represents the main application
type App struct {
	window             fyne.Window
	statusText         *widget.Entry
	containersTable    *widget.Table
	imagesTable        *widget.Table
	volumesTable       *widget.Table
	containers         []ContainerInfo
	images             []ImageInfo
	volumes            []VolumeInfo
	selectedContainers map[int]bool
	selectedImages     map[int]bool
	selectedVolumes    map[int]bool
	prerequisitesOK    bool
	activeLogStreamers []*LogStreamer
	mu                 sync.RWMutex
	statusBinding      binding.String
}

func main() {
	myApp := app.New()
	myWindow := myApp.NewWindow("Nano Whale - Docker Manager")
	myWindow.Resize(fyne.NewSize(1200, 800))

	dockerApp := &App{
		window:             myWindow,
		selectedContainers: make(map[int]bool),
		selectedImages:     make(map[int]bool),
		selectedVolumes:    make(map[int]bool),
		statusBinding:      binding.NewString(),
	}

	dockerApp.setupUI()
	dockerApp.window.SetOnClosed(dockerApp.cleanup)

	// Start prerequisite check
	go dockerApp.checkPrerequisites()

	myWindow.ShowAndRun()
}

func (a *App) setupUI() {
	// Status panel
	statusLabel := widget.NewLabel("System Status")
	statusLabel.TextStyle = fyne.TextStyle{Bold: true}

	a.statusText = widget.NewMultiLineEntry()
	a.statusText.SetMinRowsVisible(8)
	a.statusText.Disable()

	retryBtn := widget.NewButton("Retry Prerequisites Check", func() {
		go a.checkPrerequisites()
	})

	clearBtn := widget.NewButton("Clear Log", func() {
		a.statusText.SetText("")
	})

	buttonBar := container.NewHBox(retryBtn, clearBtn)
	statusPanel := container.NewBorder(statusLabel, buttonBar, nil, nil, a.statusText)

	// Create tabs
	tabs := container.NewAppTabs(
		container.NewTabItem("Containers", a.createContainerTab()),
		container.NewTabItem("Images", a.createImageTab()),
		container.NewTabItem("Volumes", a.createVolumeTab()),
	)

	// Main layout
	content := container.NewBorder(statusPanel, nil, nil, nil, tabs)
	a.window.SetContent(content)
}

func (a *App) log(message, level string) {
	timestamp := time.Now().Format("15:04:05")
	logLine := fmt.Sprintf("[%s] [%s] %s\n", timestamp, level, message)
	current := a.statusText.Text
	a.statusText.SetText(current + logLine)
}

func (a *App) cleanup() {
	a.mu.Lock()
	defer a.mu.Unlock()

	for _, streamer := range a.activeLogStreamers {
		streamer.Stop()
	}
}

// Prerequisite checking
func (a *App) checkPrerequisites() {
	a.log("Starting prerequisite check...", "INFO")

	wslOK := a.checkWSL()
	if !wslOK {
		a.log("✗ WSL 2 is not installed", "ERROR")
		a.prerequisitesOK = false
		return
	}
	a.log("✓ WSL 2 is installed", "SUCCESS")

	dockerOK := a.checkDockerEngine()
	if !dockerOK {
		a.log("✗ Docker Engine is not installed in WSL", "ERROR")
		a.prerequisitesOK = false
		return
	}
	a.log("✓ Docker Engine is installed", "SUCCESS")

	daemonOK := a.checkDockerDaemon()
	if !daemonOK {
		a.log("⚠ Docker daemon not running, attempting to start...", "WARNING")
		a.startDockerDaemon()
	} else {
		a.log("✓ Docker daemon is running", "SUCCESS")
	}

	a.prerequisitesOK = true
	a.log("✓ All prerequisites met! Docker Manager is ready.", "SUCCESS")
	a.refreshAll()
}

func (a *App) checkWSL() bool {
	cmd := exec.Command("wsl", "--status")
	return cmd.Run() == nil
}

func (a *App) checkDockerEngine() bool {
	cmd := exec.Command("wsl", "docker", "--version")
	return cmd.Run() == nil
}

func (a *App) checkDockerDaemon() bool {
	cmd := exec.Command(dockerCmdPrefix[0], append(dockerCmdPrefix[1:], "ps")...)
	return cmd.Run() == nil
}

func (a *App) startDockerDaemon() {
	cmd := exec.Command("wsl", "sudo", "service", "docker", "start")
	if err := cmd.Run(); err != nil {
		a.log(fmt.Sprintf("Failed to start Docker daemon: %v", err), "ERROR")
		return
	}
	time.Sleep(2 * time.Second)
	if a.checkDockerDaemon() {
		a.log("✓ Docker daemon started successfully", "SUCCESS")
	}
}

// Container Tab
func (a *App) createContainerTab() fyne.CanvasObject {
	// Create table
	a.containersTable = widget.NewTable(
		func() (int, int) {
			return len(a.containers) + 1, 4 // +1 for header
		},
		func() fyne.CanvasObject {
			return widget.NewLabel("template")
		},
		func(id widget.TableCellID, cell fyne.CanvasObject) {
			label := cell.(*widget.Label)
			if id.Row == 0 {
				// Header
				headers := []string{"ID", "Name", "Image", "Status"}
				label.SetText(headers[id.Col])
				label.TextStyle = fyne.TextStyle{Bold: true}
			} else if id.Row-1 < len(a.containers) {
				c := a.containers[id.Row-1]
				switch id.Col {
				case 0:
					label.SetText(c.ID[:12])
				case 1:
					label.SetText(c.Name)
				case 2:
					label.SetText(c.Image)
				case 3:
					label.SetText(c.Status)
				}
			}
		},
	)

	a.containersTable.SetColumnWidth(0, 120)
	a.containersTable.SetColumnWidth(1, 200)
	a.containersTable.SetColumnWidth(2, 250)
	a.containersTable.SetColumnWidth(3, 200)

	// Buttons
	refreshBtn := widget.NewButton("Refresh", func() { a.refreshContainers() })
	startBtn := widget.NewButton("Start", func() { a.manageContainer("start") })
	stopBtn := widget.NewButton("Stop", func() { a.manageContainer("stop") })
	restartBtn := widget.NewButton("Restart", func() { a.manageContainer("restart") })
	logsBtn := widget.NewButton("View Logs", func() { a.showLogs() })
	terminalBtn := widget.NewButton("Terminal", func() { a.openTerminal() })
	pruneBtn := widget.NewButton("Prune Exited", func() { a.pruneContainers() })

	buttons := container.NewHBox(
		refreshBtn, startBtn, stopBtn, restartBtn,
		logsBtn, terminalBtn, pruneBtn,
	)

	// ... existing table setup ...

	// --- Add the OnSelected callback here ---
	a.containersTable.OnSelected = func(id widget.TableCellID) {
		// Ignore header selection and out-of-bounds rows
		if id.Row == 0 || id.Row-1 >= len(a.containers) {
			return
		}

		a.mu.Lock()
		defer a.mu.Unlock()

		// The map should track the selected index.
		// For a single-selection scenario (like viewing logs/terminal),
		// we generally clear previous selections.

		// Clear all previous selections
		for k := range a.selectedContainers {
			delete(a.selectedContainers, k)
		}

		// Store the newly selected data index (Row - 1)
		dataIndex := id.Row - 1
		a.selectedContainers[dataIndex] = true
	}

	// ... existing table setup continues ...

	return container.NewBorder(nil, buttons, nil, nil, a.containersTable)
}

func (a *App) refreshContainers() {
	if !a.prerequisitesOK {
		return
	}

	cmd := exec.Command(dockerCmdPrefix[0],
		append(dockerCmdPrefix[1:], "ps", "-a", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}")...)
	output, err := cmd.Output()
	if err != nil {
		a.log(fmt.Sprintf("Failed to fetch containers: %v", err), "ERROR")
		return
	}

	a.mu.Lock()
	defer a.mu.Unlock()

	a.containers = []ContainerInfo{}
	lines := strings.Split(strings.TrimSpace(string(output)), "\n")
	for _, line := range lines {
		if line == "" {
			continue
		}
		parts := strings.Split(line, "\t")
		if len(parts) >= 4 {
			a.containers = append(a.containers, ContainerInfo{
				ID:     parts[0],
				Name:   parts[1],
				Image:  parts[2],
				Status: parts[3],
			})
		}
	}

	a.containersTable.Refresh()
}

func (a *App) manageContainer(action string) {
	if !a.prerequisitesOK {
		dialog.ShowInformation("Prerequisites Not Met",
			"WSL and Docker Engine must be installed first.", a.window)
		return
	}

	selected := a.getSelectedContainers()
	if len(selected) == 0 {
		dialog.ShowInformation("Selection Required",
			"Please select container(s) first.", a.window)
		return
	}

	for _, idx := range selected {
		containerID := a.containers[idx].ID
		cmd := exec.Command(dockerCmdPrefix[0],
			append(dockerCmdPrefix[1:], action, containerID)...)
		if err := cmd.Run(); err != nil {
			a.log(fmt.Sprintf("Failed to %s container %s: %v", action, containerID[:12], err), "ERROR")
		} else {
			a.log(fmt.Sprintf("Container %s %sed successfully", containerID[:12], action), "SUCCESS")
		}
	}

	a.refreshContainers()
}

func (a *App) getSelectedContainers() []int {
	var selected []int
	for idx := range a.selectedContainers {
		if a.selectedContainers[idx] {
			selected = append(selected, idx)
		}
	}
	return selected
}

func (a *App) pruneContainers() {
	dialog.ShowConfirm("Confirm Prune",
		"Are you sure you want to remove ALL stopped containers?",
		func(confirmed bool) {
			if !confirmed {
				return
			}
			cmd := exec.Command(dockerCmdPrefix[0],
				append(dockerCmdPrefix[1:], "container", "prune", "-f")...)
			if err := cmd.Run(); err != nil {
				a.log(fmt.Sprintf("Failed to prune containers: %v", err), "ERROR")
			} else {
				a.log("Stopped containers pruned successfully", "SUCCESS")
				a.refreshContainers()
			}
		}, a.window)
}

func (a *App) openTerminal() {
	selected := a.getSelectedContainers()
	if len(selected) == 0 {
		dialog.ShowInformation("Selection Required",
			"Please select a container first.", a.window)
		return
	}

	containerID := a.containers[selected[0]].ID
	cmd := exec.Command("cmd", "/C", "start", "wsl", "docker", "exec", "-it",
		containerID, "sh", "-c", "exec /bin/bash || exec /bin/sh")
	if err := cmd.Start(); err != nil {
		a.log(fmt.Sprintf("Failed to open terminal: %v", err), "ERROR")
	}
}

// Image Tab
func (a *App) createImageTab() fyne.CanvasObject {
	a.imagesTable = widget.NewTable(
		func() (int, int) {
			return len(a.images) + 1, 4
		},
		func() fyne.CanvasObject {
			return widget.NewLabel("template")
		},
		func(id widget.TableCellID, cell fyne.CanvasObject) {
			label := cell.(*widget.Label)
			if id.Row == 0 {
				headers := []string{"ID", "Repository", "Tag", "Size"}
				label.SetText(headers[id.Col])
				label.TextStyle = fyne.TextStyle{Bold: true}
			} else if id.Row-1 < len(a.images) {
				img := a.images[id.Row-1]
				switch id.Col {
				case 0:
					label.SetText(img.ID[:12])
				case 1:
					label.SetText(img.Repository)
				case 2:
					label.SetText(img.Tag)
				case 3:
					label.SetText(img.Size)
				}
			}
		},
	)

	a.imagesTable.SetColumnWidth(0, 120)
	a.imagesTable.SetColumnWidth(1, 250)
	a.imagesTable.SetColumnWidth(2, 150)
	a.imagesTable.SetColumnWidth(3, 120)

	refreshBtn := widget.NewButton("Refresh", func() { a.refreshImages() })
	removeBtn := widget.NewButton("Remove Image", func() { a.removeImages() })
	pruneBtn := widget.NewButton("Prune Dangling", func() { a.pruneImages() })

	buttons := container.NewHBox(refreshBtn, removeBtn, pruneBtn)
	return container.NewBorder(nil, buttons, nil, nil, a.imagesTable)
}

func (a *App) refreshImages() {
	if !a.prerequisitesOK {
		return
	}

	cmd := exec.Command(dockerCmdPrefix[0],
		append(dockerCmdPrefix[1:], "images", "--format", "{{.ID}}\t{{.Repository}}\t{{.Tag}}\t{{.Size}}")...)
	output, err := cmd.Output()
	if err != nil {
		a.log(fmt.Sprintf("Failed to fetch images: %v", err), "ERROR")
		return
	}

	a.mu.Lock()
	defer a.mu.Unlock()

	a.images = []ImageInfo{}
	lines := strings.Split(strings.TrimSpace(string(output)), "\n")
	for _, line := range lines {
		if line == "" {
			continue
		}
		parts := strings.Split(line, "\t")
		if len(parts) >= 4 {
			a.images = append(a.images, ImageInfo{
				ID:         parts[0],
				Repository: parts[1],
				Tag:        parts[2],
				Size:       parts[3],
			})
		}
	}

	a.imagesTable.Refresh()
}

func (a *App) removeImages() {
	selected := a.getSelectedImages()
	if len(selected) == 0 {
		dialog.ShowInformation("Selection Required",
			"Please select image(s) first.", a.window)
		return
	}

	dialog.ShowConfirm("Confirm Removal",
		fmt.Sprintf("Are you sure you want to remove %d image(s)?", len(selected)),
		func(confirmed bool) {
			if !confirmed {
				return
			}
			for _, idx := range selected {
				imageID := a.images[idx].ID
				cmd := exec.Command(dockerCmdPrefix[0],
					append(dockerCmdPrefix[1:], "rmi", "-f", imageID)...)
				if err := cmd.Run(); err != nil {
					a.log(fmt.Sprintf("Failed to remove image %s: %v", imageID[:12], err), "ERROR")
				} else {
					a.log(fmt.Sprintf("Image %s removed successfully", imageID[:12]), "SUCCESS")
				}
			}
			a.refreshImages()
		}, a.window)
}

func (a *App) getSelectedImages() []int {
	var selected []int
	for idx := range a.selectedImages {
		if a.selectedImages[idx] {
			selected = append(selected, idx)
		}
	}
	return selected
}

func (a *App) pruneImages() {
	dialog.ShowConfirm("Confirm Prune",
		"Are you sure you want to remove ALL dangling images?",
		func(confirmed bool) {
			if !confirmed {
				return
			}
			cmd := exec.Command(dockerCmdPrefix[0],
				append(dockerCmdPrefix[1:], "image", "prune", "-f")...)
			if err := cmd.Run(); err != nil {
				a.log(fmt.Sprintf("Failed to prune images: %v", err), "ERROR")
			} else {
				a.log("Dangling images pruned successfully", "SUCCESS")
				a.refreshImages()
			}
		}, a.window)
}

// Volume Tab
func (a *App) createVolumeTab() fyne.CanvasObject {
	a.volumesTable = widget.NewTable(
		func() (int, int) {
			return len(a.volumes) + 1, 2
		},
		func() fyne.CanvasObject {
			return widget.NewLabel("template")
		},
		func(id widget.TableCellID, cell fyne.CanvasObject) {
			label := cell.(*widget.Label)
			if id.Row == 0 {
				headers := []string{"Name", "Driver"}
				label.SetText(headers[id.Col])
				label.TextStyle = fyne.TextStyle{Bold: true}
			} else if id.Row-1 < len(a.volumes) {
				vol := a.volumes[id.Row-1]
				switch id.Col {
				case 0:
					label.SetText(vol.Name)
				case 1:
					label.SetText(vol.Driver)
				}
			}
		},
	)

	a.volumesTable.SetColumnWidth(0, 400)
	a.volumesTable.SetColumnWidth(1, 200)

	refreshBtn := widget.NewButton("Refresh", func() { a.refreshVolumes() })
	removeBtn := widget.NewButton("Remove Volume", func() { a.removeVolumes() })
	pruneBtn := widget.NewButton("Prune Unused", func() { a.pruneVolumes() })

	buttons := container.NewHBox(refreshBtn, removeBtn, pruneBtn)
	return container.NewBorder(nil, buttons, nil, nil, a.volumesTable)
}

func (a *App) refreshVolumes() {
	if !a.prerequisitesOK {
		return
	}

	cmd := exec.Command(dockerCmdPrefix[0],
		append(dockerCmdPrefix[1:], "volume", "ls", "--format", "{{.Name}}\t{{.Driver}}")...)
	output, err := cmd.Output()
	if err != nil {
		a.log(fmt.Sprintf("Failed to fetch volumes: %v", err), "ERROR")
		return
	}

	a.mu.Lock()
	defer a.mu.Unlock()

	a.volumes = []VolumeInfo{}
	lines := strings.Split(strings.TrimSpace(string(output)), "\n")
	for _, line := range lines {
		if line == "" {
			continue
		}
		parts := strings.Split(line, "\t")
		if len(parts) >= 2 {
			a.volumes = append(a.volumes, VolumeInfo{
				Name:   parts[0],
				Driver: parts[1],
			})
		}
	}

	a.volumesTable.Refresh()
}

func (a *App) removeVolumes() {
	selected := a.getSelectedVolumes()
	if len(selected) == 0 {
		dialog.ShowInformation("Selection Required",
			"Please select volume(s) first.", a.window)
		return
	}

	dialog.ShowConfirm("Confirm Removal",
		fmt.Sprintf("Are you sure you want to remove %d volume(s)?", len(selected)),
		func(confirmed bool) {
			if !confirmed {
				return
			}
			for _, idx := range selected {
				volumeName := a.volumes[idx].Name
				cmd := exec.Command(dockerCmdPrefix[0],
					append(dockerCmdPrefix[1:], "volume", "rm", volumeName)...)
				if err := cmd.Run(); err != nil {
					a.log(fmt.Sprintf("Failed to remove volume %s: %v", volumeName, err), "ERROR")
				} else {
					a.log(fmt.Sprintf("Volume %s removed successfully", volumeName), "SUCCESS")
				}
			}
			a.refreshVolumes()
		}, a.window)
}

func (a *App) getSelectedVolumes() []int {
	var selected []int
	for idx := range a.selectedVolumes {
		if a.selectedVolumes[idx] {
			selected = append(selected, idx)
		}
	}
	return selected
}

func (a *App) pruneVolumes() {
	dialog.ShowConfirm("Confirm Prune",
		"Are you sure you want to remove ALL unused volumes?",
		func(confirmed bool) {
			if !confirmed {
				return
			}
			cmd := exec.Command(dockerCmdPrefix[0],
				append(dockerCmdPrefix[1:], "volume", "prune", "-f")...)
			if err := cmd.Run(); err != nil {
				a.log(fmt.Sprintf("Failed to prune volumes: %v", err), "ERROR")
			} else {
				a.log("Unused volumes pruned successfully", "SUCCESS")
				a.refreshVolumes()
			}
		}, a.window)
}

// Log viewing
func (a *App) showLogs() {
	selected := a.getSelectedContainers()
	if len(selected) == 0 {
		dialog.ShowInformation("Selection Required",
			"Please select a container first.", a.window)
		return
	}

	containerID := a.containers[selected[0]].ID
	containerName := a.containers[selected[0]].Name

	// FIX: Replaced a.window.Driver().AllWindows()... with a.window
	logDialog := dialog.NewCustom(
		fmt.Sprintf("Logs: %s", containerName),
		"Close",
		a.createLogViewer(containerID),
		a.window, // Pass the main window as the parent
	)
	logDialog.Resize(fyne.NewSize(800, 600))
	logDialog.Show()
}

func (a *App) createLogViewer(containerID string) fyne.CanvasObject {
	logText := widget.NewMultiLineEntry()
	logText.SetMinRowsVisible(20)
	logText.Disable()

	streamer := NewLogStreamer(containerID, logText, true)
	a.mu.Lock()
	a.activeLogStreamers = append(a.activeLogStreamers, streamer)
	a.mu.Unlock()

	go streamer.Start()

	return container.NewBorder(nil, nil, nil, nil, logText)
}

func (a *App) refreshAll() {
	a.refreshContainers()
	a.refreshImages()
	a.refreshVolumes()
}

// LogStreamer implementation
func NewLogStreamer(containerID string, textWidget *widget.Entry, showTimestamps bool) *LogStreamer {
	_, cancel := context.WithCancel(context.Background())
	return &LogStreamer{
		containerID:    containerID,
		cancel:         cancel,
		running:        true,
		showTimestamps: showTimestamps,
		// FIX: Assign the passed widget here
		textWidget: textWidget,
	}
}

func (s *LogStreamer) Start() {
	s.mu.Lock()
	defer s.mu.Unlock()

	args := append(dockerCmdPrefix[1:], "logs", "-f")
	if s.showTimestamps {
		args = append(args, "-t")
	}
	if s.sinceTime != "" {
		args = append(args, fmt.Sprintf("--since=%s", s.sinceTime))
	}
	args = append(args, s.containerID)

	s.cmd = exec.Command(dockerCmdPrefix[0], args...)
	stdout, err := s.cmd.StdoutPipe()
	if err != nil {
		return
	}

	if err := s.cmd.Start(); err != nil {
		return
	}

	scanner := bufio.NewScanner(stdout)
	for scanner.Scan() && s.running {
		line := scanner.Text() + "\n"

		// FIX: Safely update the widget content
		currentText := s.textWidget.Text
		s.textWidget.SetText(currentText + line)

		// Call Refresh to ensure the change is drawn to the screen
		// Fyne's internal queue handles this refresh safely.
		s.textWidget.Refresh()
	}
}

func (s *LogStreamer) Stop() {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.running = false
	if s.cancel != nil {
		s.cancel()
	}
	if s.cmd != nil && s.cmd.Process != nil {
		s.cmd.Process.Kill()
	}
}
