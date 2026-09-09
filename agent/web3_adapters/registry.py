"""
Passport Adapter Registry — ZK-KYC Compliance Agent (zkkyc.adapters.registry)

Spec reference: EP-08 (F-08.1 — US-08.1.1)

The `AdapterRegistry` is a singleton-ish mapping from `chain_target` strings
to `PassportAdapterBase` instances. The Settlement Agent (EP-06 F-06.1.5)
resolves adapters exclusively through `AdapterRegistry.get(state.chain_target)`
— no `if/elif chain_target ==` branching exists in agent code.

Registration contract:
  - Keys are lowercase chain_target strings: "stellar", "casper", "ethereum",
    "polkadot", "hedera", etc.
  - Values are PassportAdapterBase subclasses or instances.
  - register() accepts both classes (instantiated once, lazily) and instances.
  - The registry raises KeyError with a descriptive message if a chain target
    is not registered, rather than returning None and causing a downstream
    AttributeError.
"""

from __future__ import annotations

import logging
from typing import TypeVar

from .base import (
    AdapterConformanceError,
    AdapterDeploymentError,
    PassportAdapterBase,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=PassportAdapterBase)


class AdapterRegistry:
    """Thread-safe, lazy-instantiated adapter registry.

    Usage:
        registry = get_adapter_registry()
        adapter = registry.get("stellar")
        result = await adapter.verify_credential(wallet, policy_id)
    """

    def __init__(self) -> None:
        self._adapters: dict[str, PassportAdapterBase] = {}
        self._classes: dict[str, type[PassportAdapterBase]] = {}
        self._lock = __import__("asyncio").Lock()

    async def register(
        self,
        chain_target: str,
        adapter: type[PassportAdapterBase] | PassportAdapterBase,
    ) -> None:
        """Register an adapter class or instance under `chain_target`.

        Args:
            chain_target: lowercase chain identifier (e.g. "stellar", "ethereum").
            adapter: either a PassportAdapterBase subclass (instantiated lazily)
                or a ready-made instance.
        """
        chain_target = chain_target.lower().strip()
        if not chain_target:
            raise AdapterConformanceError("registry", "chain_target must not be empty")

        async with self._lock:
            if isinstance(adapter, type) and issubclass(adapter, PassportAdapterBase):
                self._classes[chain_target] = adapter
                logger.info(
                    "adapter class registered",
                    extra={"chain_target": chain_target, "adapter": adapter.__name__},
                )
            elif isinstance(adapter, PassportAdapterBase):
                self._adapters[chain_target] = adapter
                logger.info(
                    "adapter instance registered",
                    extra={"chain_target": chain_target, "adapter": repr(adapter)},
                )
            else:
                raise AdapterConformanceError(
                    "registry",
                    f"adapter must be a PassportAdapterBase subclass or instance; "
                    f"got {type(adapter).__name__}",
                )

    async def get(self, chain_target: str) -> PassportAdapterBase:
        """Resolve an adapter instance for `chain_target`.

        Lazily instantiates registered classes on first access. Caches the
        instance for subsequent calls.

        Args:
            chain_target: lowercase chain identifier.

        Returns:
            A PassportAdapterBase instance ready for use.

        Raises:
            KeyError: if `chain_target` is not registered. The error message
                includes the list of registered chains to aid debugging.
        """
        chain_target = chain_target.lower().strip()

        # Fast path: already an instance
        if chain_target in self._adapters:
            return self._adapters[chain_target]

        # Lazy instantiation from registered class
        if chain_target in self._classes:
            async with self._lock:
                if chain_target not in self._adapters:
                    cls = self._classes[chain_target]
                    try:
                        instance = cls()
                    except Exception as exc:
                        raise AdapterDeploymentError(
                            chain_target,
                            f"failed to instantiate adapter {cls.__name__}: {exc}",
                            cause=exc,
                        ) from exc
                    self._adapters[chain_target] = instance
                    logger.info(
                        "adapter lazily instantiated",
                        extra={"chain_target": chain_target, "adapter": cls.__name__},
                    )
                return self._adapters[chain_target]

        available = ", ".join(sorted(self.list_available())) or "(none)"
        raise KeyError(
            f"No adapter registered for chain_target '{chain_target}'. "
            f"Registered adapters: {available}. "
            f"See agent.web3_adapters.registry and docs/p11_web3_defi_expansion.md."
        )

    def list_available(self) -> set[str]:
        """Return the set of all registered chain targets (classes + instances)."""
        return set(self._classes) | set(self._adapters)

    def is_registered(self, chain_target: str) -> bool:
        """Return True if `chain_target` has a registered adapter."""
        return chain_target.lower().strip() in self.list_available()


# ---------------------------------------------------------------------------
# Module-level singleton — the Settlement Agent imports this directly.
# ---------------------------------------------------------------------------

_registry: AdapterRegistry | None = None


def get_adapter_registry() -> AdapterRegistry:
    """Return the global AdapterRegistry singleton.

    Initialises the registry on first call and auto-registers built-in
    adapters that are importable. This means `registry.get("stellar")` works
    as long as `stellar_sdk` is installed, without explicit registration.
    """
    global _registry
    if _registry is None:
        _registry = AdapterRegistry()
        _auto_register_builtins(_registry)
    return _registry


def _auto_register_builtins(registry: AdapterRegistry) -> None:
    """Auto-register adapters whose dependencies are installed.

    Keeps the Settlement Agent simple: it never needs to know which adapters
    are available. If the import fails (dependency not installed), the
    adapter simply isn't registered and get_adapter_registry().get("stellar")
    will raise KeyError with the list of available adapters.
    """
    import importlib

    builtin_adapters = [
        ("sepolia-evm", "EVMAdapter"),
    ]

    for chain_target, class_name in builtin_adapters:
        # Dual-import safety: the `agent` package prefix resolves in the API
        # container (cwd=/app), the bare name in agent-worker (cwd=agent/).
        module_path = None
        for candidate in ("agent.web3_adapters.ethereum", "web3_adapters.ethereum"):
            try:
                mod = importlib.import_module(candidate)
                module_path = candidate
                break
            except ImportError:
                continue
        if module_path is None:
            logger.debug(
                "builtin adapter not registered (module not importable)",
                extra={"chain_target": chain_target},
            )
            continue
        try:
            cls = getattr(mod, class_name)
            # register class (not instance) — lazy instantiation on first get()
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're inside a running loop (e.g. FastAPI startup).
                    # Schedule registration as a task.
                    loop.create_task(registry.register(chain_target, cls))
                else:
                    loop.run_until_complete(registry.register(chain_target, cls))
            except RuntimeError:
                # No event loop — register synchronously via a quick run
                import asyncio
                asyncio.run(registry.register(chain_target, cls))
        except (ImportError, AttributeError) as exc:
            logger.debug(
                "builtin adapter not registered (missing dependency)",
                extra={"chain_target": chain_target, "reason": str(exc)},
            )
        except Exception as exc:
            logger.warning(
                "failed to auto-register builtin adapter",
                extra={"chain_target": chain_target, "error": str(exc)},
            )
