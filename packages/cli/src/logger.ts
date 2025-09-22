import * as cliProgress from "cli-progress";

export class SimpleLogger {
  private progressBar: cliProgress.SingleBar | null = null;
  private isDebugMode = false;

  constructor() {
    this.isDebugMode = !!process.env.DEBUG;
  }

  info(message: string) {
    if (this.progressBar) {
      this.progressBar.stop();
      this.progressBar = null;
    }
    console.log(`[INFO] ${message}`);
  }

  error(message: string) {
    if (this.progressBar) {
      this.progressBar.stop();
      this.progressBar = null;
    }
    console.error(`[ERROR] ${message}`);
  }

  debug(message: string) {
    if (this.isDebugMode) {
      if (this.progressBar) {
        this.progressBar.stop();
        this.progressBar = null;
      }
      console.log(`[DEBUG] ${message}`);
    }
  }

  startProgress(total: number, startValue = 0) {
    if (!this.isDebugMode) {
      this.progressBar = new cliProgress.SingleBar({
        format: "Progress |{bar}| {percentage}% | {value}/{total} files | ETA: {eta_formatted}",
        barCompleteChar: "\u2588",
        barIncompleteChar: "\u2591",
        hideCursor: true,
      });
      this.progressBar.start(total, startValue);
    }
  }

  updateProgress(value: number, payload?: Record<string, unknown>) {
    if (this.progressBar) {
      this.progressBar.update(value, payload);
    }
  }

  stopProgress() {
    if (this.progressBar) {
      this.progressBar.stop();
      this.progressBar = null;
    }
  }
}
