import { Command } from "commander";

export interface CliOptions {
  mode: "cpg" | "template" | "ast" | "dfg";
  data: string;
  output?: string;
  ext?: string[];
  replaceMacro: boolean;
  keepIntermediate: boolean;
  debug?: boolean;
  verbose?: boolean;
}

export class CliParser {
  private program: Command;
  private parsedOptions: CliOptions | null = null;

  constructor() {
    this.program = new Command();
    this.setupProgram();
  }

  private setupProgram(): void {
    this.program
      .name("ssat")
      .description("Static Software Analysis Tool - Convert C source code to various representations")
      .version("2.4.3")
      .addCommand(this.createCpgCommand())
      .addCommand(this.createTemplateCommand())
      .addCommand(this.createAstCommand())
      .addCommand(this.createDfgCommand())
      .helpCommand("help", "Display help for command")
      .configureHelp({
        sortSubcommands: true,
        showGlobalOptions: true,
      });
  }

  private createCpgCommand(): Command {
    return new Command("cpg")
      .description("Generate Code Property Graph from C source code")
      .requiredOption("-d, --data <path>", "Input C source file or directory")
      .option("-o, --output <path>", "Output directory (default: result/cpg_<timestamp>)")
      .option("--ext <extensions>", "File extensions to process (comma-separated)", "c")
      .option("--replace-macro", "Replace macros in source files", true)
      .option("--no-replace-macro", "Skip macro replacement")
      .option("--keep-intermediate", "Keep intermediate files")
      .option("-v, --verbose", "Verbose output")
      .option("--debug", "Enable debug mode")
      .action((options: Record<string, unknown>) => {
        const data = options.data as string;
        if (!data) {
          console.error("Error: --data is required");
          process.exit(1);
        }
        this.handleCommand("cpg", data, options);
      });
  }

  private createTemplateCommand(): Command {
    return new Command("template")
      .description("Generate Template artifacts from CPG data")
      .requiredOption("-d, --data <path>", "Input CPG file or directory")
      .option("-o, --output <path>", "Output directory (default: result/template_<timestamp>)")
      .option("--ext <extensions>", "File extensions to process (comma-separated)", "json")
      .option("--keep-intermediate", "Keep intermediate files")
      .option("-v, --verbose", "Verbose output")
      .option("--debug", "Enable debug mode")
      .action((options: Record<string, unknown>) => {
        const data = options.data as string;
        if (!data) {
          console.error("Error: --data is required");
          process.exit(1);
        }
        this.handleCommand("template", data, options);
      });
  }

  private createAstCommand(): Command {
    return new Command("ast")
      .description("Generate Abstract Syntax Tree from Template data")
      .requiredOption("-d, --data <path>", "Input Template file or directory")
      .option("-o, --output <path>", "Output directory (default: result/ast_<timestamp>)")
      .option("--ext <extensions>", "File extensions to process (comma-separated)", "json")
      .option("--keep-intermediate", "Keep intermediate files")
      .option("-v, --verbose", "Verbose output")
      .option("--debug", "Enable debug mode")
      .action((options: Record<string, unknown>) => {
        const data = options.data as string;
        if (!data) {
          console.error("Error: --data is required");
          process.exit(1);
        }
        this.handleCommand("ast", data, options);
      });
  }

  private createDfgCommand(): Command {
    return new Command("dfg")
      .description("Generate Data Flow Graph from Template data")
      .requiredOption("-d, --data <path>", "Input Template file or directory")
      .option("-o, --output <path>", "Output directory (default: result/dfg_<timestamp>)")
      .option("--ext <extensions>", "File extensions to process (comma-separated)", "json")
      .option("--keep-intermediate", "Keep intermediate files")
      .option("-v, --verbose", "Verbose output")
      .option("--debug", "Enable debug mode")
      .action((options: Record<string, unknown>) => {
        const data = options.data as string;
        if (!data) {
          console.error("Error: --data is required");
          process.exit(1);
        }
        this.handleCommand("dfg", data, options);
      });
  }

  private handleCommand(mode: CliOptions["mode"], input: string, options: Record<string, unknown>): void {
    this.parsedOptions = {
      mode,
      data: input,
      output: options.output as string | undefined,
      ext: options.ext && typeof options.ext === "string" ? options.ext.split(",").map((e: string) => e.trim()) : undefined,
      replaceMacro: options.replaceMacro !== false,
      keepIntermediate: Boolean(options.keepIntermediate),
      debug: Boolean(options.debug),
      verbose: Boolean(options.verbose),
    };
  }

  parse(): CliOptions {
    try {
      this.program.parse();

      if (!this.parsedOptions) {
        console.error("Error: No valid command specified");
        this.program.help();
        process.exit(1);
      }

      return this.parsedOptions;
    } catch (error) {
      console.error("Error parsing command:", error instanceof Error ? error.message : String(error));
      this.program.help();
      process.exit(1);
    }
  }
}
