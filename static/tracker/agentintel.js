(function () {
  const COOKIE_NAME = "ai_agent_session";

  function uuid() {
    if (window.crypto && window.crypto.randomUUID) {
      return window.crypto.randomUUID();
    }
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (char) {
      const rand = (Math.random() * 16) | 0;
      const value = char === "x" ? rand : (rand & 0x3) | 0x8;
      return value.toString(16);
    });
  }

  function readCookie(name) {
    const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
    return match ? decodeURIComponent(match[2]) : null;
  }

  function setCookie(name, value) {
    document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=31536000; SameSite=Lax`;
  }

  function getSessionId() {
    const existing = readCookie(COOKIE_NAME) || window.localStorage.getItem(COOKIE_NAME);
    if (existing) return existing;
    const created = uuid();
    setCookie(COOKIE_NAME, created);
    window.localStorage.setItem(COOKIE_NAME, created);
    return created;
  }

  function detectResourceType(name) {
    const lowered = (name || "").toLowerCase();
    if (/\.(png|jpg|jpeg|gif|svg|webp)$/.test(lowered)) return "image";
    if (/\.js$/.test(lowered)) return "script";
    if (/\.css$/.test(lowered)) return "stylesheet";
    if (/\.(pdf|doc|docx|xls|xlsx|ppt|pptx|txt|csv)$/.test(lowered)) return "document";
    if (/\.(zip|tar|gz|rar|7z)$/.test(lowered)) return "archive";
    if (/\.(mp4|mp3|mov|wav|m4a)$/.test(lowered)) return "media";
    if (/(\.html?$)|\/$/.test(lowered)) return "page";
    return "other";
  }

  function buildHeaders(token) {
    return {
      "Content-Type": "application/json",
      "X-Site-Token": token,
    };
  }

  function send(url, payload, token) {
    fetch(url, {
      method: "POST",
      headers: buildHeaders(token),
      body: JSON.stringify(payload),
      keepalive: true,
      credentials: "omit",
    }).catch(function () {});
  }

  function browserCapabilities() {
    return {
      webdriver: navigator.webdriver === true,
      languages: navigator.languages || [],
      hardwareConcurrency: navigator.hardwareConcurrency || 0,
      deviceMemory: navigator.deviceMemory || 0,
      platform: navigator.platform || "",
      doNotTrack: navigator.doNotTrack || "",
    };
  }

  function buildPagePayload(config, eventType) {
    const url = new URL(window.location.href);
    return {
      siteId: config.siteId,
      sessionId: getSessionId(),
      eventType: eventType || "page_view",
      path: url.pathname,
      query: url.search,
      referrer: document.referrer || "",
      utmSource: url.searchParams.get("utm_source") || "",
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "",
      screen: {
        width: window.screen.width,
        height: window.screen.height,
      },
      browserCapabilities: browserCapabilities(),
      userAgent: navigator.userAgent,
    };
  }

  function collectResources(config) {
    if (!config.trackResources || !window.performance || !performance.getEntriesByType) return;
    const entries = performance.getEntriesByType("resource").slice(-25);
    if (!entries.length) return;
    const resources = entries.map(function (entry) {
      const url = new URL(entry.name, window.location.origin);
      return {
        path: url.pathname,
        url: entry.name,
        transferSize: entry.transferSize || 0,
        contentType: "",
        resourceType: detectResourceType(url.pathname),
        action: "observed",
      };
    });
    send(config.collectorUrl + "/api/ingest/resource", {
      siteId: config.siteId,
      sessionId: getSessionId(),
      path: window.location.pathname,
      userAgent: navigator.userAgent,
      resources: resources,
    }, config.token);
  }

  function hookDownloads(config) {
    if (!config.trackDownloads) return;
    document.addEventListener("click", function (event) {
      const anchor = event.target.closest("a[href]");
      if (!anchor) return;
      const href = anchor.getAttribute("href") || "";
      if (!/\.(pdf|zip|docx?|xlsx?|pptx?|csv|txt)$/i.test(href)) return;
      send(config.collectorUrl + "/api/ingest/resource", {
        siteId: config.siteId,
        sessionId: getSessionId(),
        path: window.location.pathname,
        userAgent: navigator.userAgent,
        resources: [
          {
            path: anchor.pathname || href,
            url: anchor.href,
            transferSize: 0,
            resourceType: detectResourceType(anchor.pathname || href),
            action: "download_click",
          },
        ],
      }, config.token);
    });
  }

  window.AIAgentTracker = {
    init: function init(rawConfig) {
      const config = Object.assign({
        trackResources: true,
        trackDownloads: true,
        sampleRate: 1.0,
      }, rawConfig || {});

      if (!config.siteId || !config.collectorUrl || !config.token) {
        throw new Error("AIAgentTracker requires siteId, collectorUrl, and token.");
      }
      if (Math.random() > config.sampleRate) return;

      const trackPage = function (eventType) {
        send(config.collectorUrl + "/api/ingest/browser", buildPagePayload(config, eventType), config.token);
        collectResources(config);
      };

      trackPage("page_view");
      hookDownloads(config);

      const originalPushState = history.pushState;
      history.pushState = function () {
        originalPushState.apply(history, arguments);
        window.setTimeout(function () {
          trackPage("spa_navigation");
        }, 25);
      };
      window.addEventListener("popstate", function () {
        trackPage("spa_navigation");
      });
    }
  };
})();
