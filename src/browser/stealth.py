"""
Anti-detection stealth patches for Playwright.

Applies JavaScript patches to mask automation fingerprints, making the
browser appear as a regular user session rather than an automated script.
"""

from __future__ import annotations

from playwright.async_api import Page

from src.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Stealth scripts to inject before any page navigation
# ---------------------------------------------------------------------------
STEALTH_SCRIPTS = [
    # 1. Remove navigator.webdriver flag
    """
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
    });
    """,
    # 2. Override navigator.plugins to appear non-empty
    """
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const plugins = [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client', filename: 'internal-nacl-plugin' },
            ];
            plugins.length = 3;
            return plugins;
        },
    });
    """,
    # 3. Override navigator.languages
    """
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-IN', 'en-US', 'en'],
    });
    """,
    # 4. Inject window.chrome runtime object
    """
    window.chrome = {
        runtime: {
            onMessage: { addListener: function() {}, removeListener: function() {} },
            sendMessage: function() {},
            connect: function() { return { onMessage: { addListener: function() {} } }; },
        },
        loadTimes: function() { return {}; },
        csi: function() { return {}; },
        app: { isInstalled: false, InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }, RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' } },
    };
    """,
    # 5. Fix permissions query
    """
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters)
    );
    """,
    # 6. Override navigator.platform
    """
    Object.defineProperty(navigator, 'platform', {
        get: () => 'Win32',
    });
    """,
    # 7. Override navigator.hardwareConcurrency
    """
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => 8,
    });
    """,
    # 8. Override navigator.deviceMemory
    """
    Object.defineProperty(navigator, 'deviceMemory', {
        get: () => 8,
    });
    """,
    # 9. Prevent detection via toString checks
    """
    const oldCall = Function.prototype.call;
    function newCall(...args) {
        if (this === window.navigator.permissions.query) {
            return oldCall.apply(this, args);
        }
        return oldCall.apply(this, args);
    }
    // We avoid overriding Function.prototype.call to prevent breakage
    """,
    # 10. Fix WebGL vendor/renderer info
    """
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        // UNMASKED_VENDOR_WEBGL
        if (parameter === 37445) {
            return 'Google Inc. (NVIDIA)';
        }
        // UNMASKED_RENDERER_WEBGL
        if (parameter === 37446) {
            return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 Direct3D11 vs_5_0 ps_5_0)';
        }
        return getParameter.apply(this, arguments);
    };
    """,
]


async def apply_stealth_scripts(page: Page) -> None:
    """
    Apply all stealth patches to a Playwright page.

    These scripts are injected via add_init_script, which ensures they
    run before any page JavaScript, on every navigation.

    Args:
        page: The Playwright Page to patch.
    """
    combined_script = "\n".join(STEALTH_SCRIPTS)

    await page.add_init_script(combined_script)

    logger.debug("Stealth scripts applied successfully")
