"""
Anti-detection stealth patches for Playwright — LinkedIn-specific.

Applies JavaScript patches to mask automation fingerprints, making the
browser appear as a regular user session. LinkedIn has aggressive bot
detection, so these patches are more comprehensive than the Naukri version.
"""

from __future__ import annotations

from playwright.async_api import Page

from src.linked_agent.bot.interfaces import IStealthPatcher
from src.linked_agent.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Stealth scripts — LinkedIn-specific (more aggressive than Naukri)
# ---------------------------------------------------------------------------
STEALTH_SCRIPTS = [
    # 1. Remove navigator.webdriver flag (critical for LinkedIn)
    """
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
    });
    delete navigator.__proto__.webdriver;
    """,
    # 2. Override navigator.plugins to appear non-empty
    """
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const plugins = [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
            ];
            plugins.length = 3;
            return plugins;
        },
    });
    """,
    # 3. Override navigator.languages
    """
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });
    """,
    # 4. Inject window.chrome runtime object (LinkedIn checks this)
    """
    window.chrome = {
        runtime: {
            onMessage: { addListener: function() {}, removeListener: function() {} },
            sendMessage: function() {},
            connect: function() { return { onMessage: { addListener: function() {} } }; },
            onConnect: { addListener: function() {} },
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
    # 9. Fix WebGL vendor/renderer info
    """
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) { return 'Google Inc. (NVIDIA)'; }
        if (parameter === 37446) { return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 Direct3D11 vs_5_0 ps_5_0)'; }
        return getParameter.apply(this, arguments);
    };
    """,
    # 10. Spoof connection info (LinkedIn monitors network conditions)
    """
    Object.defineProperty(navigator, 'connection', {
        get: () => ({
            effectiveType: '4g',
            rtt: 50,
            downlink: 10.0,
            saveData: false,
        }),
    });
    """,
    # 11. Override Date.now() to add slight jitter (prevents timing fingerprint)
    """
    const _originalDateNow = Date.now;
    Date.now = function() {
        return _originalDateNow() + Math.floor(Math.random() * 5);
    };
    """,
    # 12. Override performance.now() with jitter
    """
    const _originalPerformanceNow = performance.now.bind(performance);
    performance.now = function() {
        return _originalPerformanceNow() + Math.random() * 0.1;
    };
    """,
    # 13. Prevent LinkedIn-specific automation detection via CDP
    """
    // Override the CDP Runtime.enable detection
    const originalGetOwnPropertyDescriptor = Object.getOwnPropertyDescriptor;
    Object.getOwnPropertyDescriptor = function(obj, prop) {
        if (obj === navigator && prop === 'webdriver') {
            return undefined;
        }
        return originalGetOwnPropertyDescriptor(obj, prop);
    };
    """,
    # 14. Spoof screen dimensions to match viewport
    """
    Object.defineProperty(screen, 'width', { get: () => 1920 });
    Object.defineProperty(screen, 'height', { get: () => 1080 });
    Object.defineProperty(screen, 'availWidth', { get: () => 1920 });
    Object.defineProperty(screen, 'availHeight', { get: () => 1040 });
    Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
    """,
]


class LinkedInStealthPatcher(IStealthPatcher):
    """
    Injects specialized anti-detection scripts into Playwright pages.
    LinkedIn-specific with enhanced stealth measures.
    """

    def __init__(self, scripts: list[str] | None = None) -> None:
        self.scripts = scripts if scripts is not None else STEALTH_SCRIPTS

    async def apply(self, page: Page) -> None:
        """
        Apply all stealth patches to a Playwright page.

        These scripts are injected via add_init_script, which ensures they
        run before any page JavaScript, on every navigation.
        """
        combined_script = "\n".join(self.scripts)
        await page.add_init_script(combined_script)
        logger.debug("LinkedIn stealth scripts applied successfully")
