import importlib
import importlib.util
import os
import sys
from contextlib import contextmanager
from types import ModuleType
from typing import Dict, List


class PathResolver:
    """A class for resolving paths within the monorepo structure."""

    def __init__(self):
        """Initialize the path resolver with base directories."""
        self._base_directories = self._get_base_directories()

    def _get_base_directories(self) -> Dict[str, str]:
        """Get base directories for all packages and repo root."""
        current_dir = os.path.dirname(__file__)  # packages/agent/utils/
        agent_dir = os.path.dirname(current_dir)  # packages/agent/
        packages_dir = os.path.dirname(agent_dir)  # packages/
        repo_root = os.path.dirname(packages_dir)  # root/

        return {
            "agent": agent_dir,
            "core": os.path.join(packages_dir, "core"),
            "cli": os.path.join(packages_dir, "cli"),
            "prisma": os.path.join(packages_dir, "prisma"),
            "web": os.path.join(repo_root, "web"),
            "repo_root": repo_root,
            "packages": packages_dir,
        }

    def _resolve_path_from_base(self, base_name: str, relative_path: str) -> str:
        """Resolve a relative path from a base directory."""
        if base_name not in self._base_directories:
            raise ValueError(
                f"Unknown base directory: {base_name}. Available: {list(self._base_directories.keys())}"
            )

        base_dir = self._base_directories[base_name]
        return os.path.join(base_dir, relative_path)

    # Package-specific path resolution methods
    def from_core_package(self, relative_path: str) -> str:
        """Resolve path relative to the core package directory."""
        return self._resolve_path_from_base("core", relative_path)

    def from_agent_package(self, relative_path: str) -> str:
        """Resolve path relative to the agent package directory."""
        return self._resolve_path_from_base("agent", relative_path)

    def from_cli_package(self, relative_path: str) -> str:
        """Resolve path relative to the CLI package directory."""
        return self._resolve_path_from_base("cli", relative_path)

    def from_prisma_package(self, relative_path: str) -> str:
        """Resolve path relative to the prisma package directory."""
        return self._resolve_path_from_base("prisma", relative_path)

    def from_web_package(self, relative_path: str) -> str:
        """Resolve path relative to the web package directory."""
        return self._resolve_path_from_base("web", relative_path)

    def from_repo_root(self, relative_path: str) -> str:
        """Resolve path relative to the repository root directory."""
        return self._resolve_path_from_base("repo_root", relative_path)

    def from_packages(self, relative_path: str) -> str:
        """Resolve path relative to the packages directory."""
        return self._resolve_path_from_base("packages", relative_path)

    # Generic utility methods
    def get_package_path(self, package_name: str) -> str:
        """Get the absolute path to a specific package directory."""
        return self._resolve_path_from_base(package_name, "")

    def list_available_packages(self) -> List[str]:
        """List all available package names."""
        return list(self._base_directories.keys())

    def get_base_directories(self) -> Dict[str, str]:
        """Get a copy of all base directories."""
        return self._base_directories.copy()

    def exists(self, package_name: str, relative_path: str = "") -> bool:
        """Check if a path exists within a package."""
        try:
            full_path = self._resolve_path_from_base(package_name, relative_path)
            return os.path.exists(full_path)
        except ValueError:
            return False

    def is_file(self, package_name: str, relative_path: str) -> bool:
        """Check if a path is a file within a package."""
        try:
            full_path = self._resolve_path_from_base(package_name, relative_path)
            return os.path.isfile(full_path)
        except ValueError:
            return False

    def is_dir(self, package_name: str, relative_path: str) -> bool:
        """Check if a path is a directory within a package."""
        try:
            full_path = self._resolve_path_from_base(package_name, relative_path)
            return os.path.isdir(full_path)
        except ValueError:
            return False

    # --- Import utilities ---
    def _ensure_on_sys_path(self, path: str, append: bool = False) -> None:
        """Ensure a directory is present on sys.path."""
        if path and os.path.isdir(path):
            if path not in sys.path:
                if append:
                    sys.path.append(path)
                else:
                    sys.path.insert(0, path)

    def add_base_to_sys_path(self, base_name: str, append: bool = False) -> str:
        """Add the base directory to sys.path and return it."""
        base = self.get_package_path(base_name)
        self._ensure_on_sys_path(base, append=append)
        return base

    def add_all_bases_to_sys_path(self, append: bool = False) -> None:
        """Add all known base directories to sys.path."""
        for base in self._base_directories.values():
            self._ensure_on_sys_path(base, append=append)

    @contextmanager
    def sys_path_context(self, path: str, append: bool = False):
        """Temporarily add a directory to sys.path for the duration of a context."""
        added = False
        if path and os.path.isdir(path) and path not in sys.path:
            if append:
                sys.path.append(path)
            else:
                sys.path.insert(0, path)
            added = True
        try:
            yield
        finally:
            if added:
                try:
                    sys.path.remove(path)
                except ValueError:
                    pass

    @contextmanager
    def base_sys_path_context(self, base_name: str, append: bool = False):
        """Temporarily add a base directory to sys.path within a context."""
        base = self.get_package_path(base_name)
        with self.sys_path_context(base, append=append):
            yield

    def import_module_from_base(self, base_name: str, dotted_module: str) -> ModuleType:
        """Import a module by dotted path after adding a base directory to sys.path.

        Example:
            import_module_from_base("core", "types.node")
        """
        self.add_base_to_sys_path(base_name)
        return importlib.import_module(dotted_module)

    def import_from_file(self, module_name: str, file_path: str) -> ModuleType:
        """Import a module from an explicit file path.

        Args:
            module_name: Name to assign to the loaded module
            file_path: Absolute or relative path to a .py file
        """
        abs_path = os.path.abspath(file_path)
        spec = importlib.util.spec_from_file_location(module_name, abs_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from path: {file_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)  # type: ignore[assignment]
        return module


# Create a singleton instance for easy importing
path_resolver = PathResolver()


# Backward compatibility functions (deprecated but still functional)
def resolvePathFromCorePackage(relativePath: str) -> str:
    """Resolve path relative to the core package directory. (Deprecated: use PathResolver.from_core_package)"""
    return path_resolver.from_core_package(relativePath)


def resolvePathFromAgentPackage(relativePath: str) -> str:
    """Resolve path relative to the agent package directory. (Deprecated: use PathResolver.from_agent_package)"""
    return path_resolver.from_agent_package(relativePath)


def resolvePathFromCliPackage(relativePath: str) -> str:
    """Resolve path relative to the CLI package directory. (Deprecated: use PathResolver.from_cli_package)"""
    return path_resolver.from_cli_package(relativePath)


def resolvePathFromPrismaPackage(relativePath: str) -> str:
    """Resolve path relative to the prisma package directory. (Deprecated: use PathResolver.from_prisma_package)"""
    return path_resolver.from_prisma_package(relativePath)


def resolvePathFromWebPackage(relativePath: str) -> str:
    """Resolve path relative to the web package directory. (Deprecated: use PathResolver.from_web_package)"""
    return path_resolver.from_web_package(relativePath)


def resolvePathFromRepoRoot(relativePath: str) -> str:
    """Resolve path relative to the repository root directory. (Deprecated: use PathResolver.from_repo_root)"""
    return path_resolver.from_repo_root(relativePath)


def resolvePathFromPackages(relativePath: str) -> str:
    """Resolve path relative to the packages directory. (Deprecated: use PathResolver.from_packages)"""
    return path_resolver.from_packages(relativePath)


def get_package_path(package_name: str) -> str:
    """Get the absolute path to a specific package directory. (Deprecated: use PathResolver.get_package_path)"""
    return path_resolver.get_package_path(package_name)


def list_available_packages() -> list:
    """List all available package names. (Deprecated: use PathResolver.list_available_packages)"""
    return path_resolver.list_available_packages()


# Import helper convenience wrappers
def add_base_to_sys_path(base_name: str, append: bool = False) -> str:
    return path_resolver.add_base_to_sys_path(base_name, append=append)


def add_all_bases_to_sys_path(append: bool = False) -> None:
    path_resolver.add_all_bases_to_sys_path(append=append)


def import_module_from_base(base_name: str, dotted_module: str) -> ModuleType:
    return path_resolver.import_module_from_base(base_name, dotted_module)


def import_from_file(module_name: str, file_path: str) -> ModuleType:
    return path_resolver.import_from_file(module_name, file_path)
