(function () {
  "use strict";

  const canvas = document.getElementById("pet-canvas");
  const context = canvas.getContext("2d", { alpha: true });
  const NUMBER_PROPERTIES = new Set([
    "x", "y", "rotation", "scale", "scaleX", "scaleY", "opacity"
  ]);
  const ANIMATED_PROPERTIES = new Set([...NUMBER_PROPERTIES, "visible"]);

  const status = {
    ready: false,
    loading: false,
    error: null,
    packageUrl: null,
    requestedState: "idle",
    activeAnimation: null,
    targetFps: 60,
    measuredFps: 0,
    frameCount: 0,
    partCount: 0,
    canvasWidth: 0,
    canvasHeight: 0
  };

  let scene = null;
  let loadVersion = 0;
  let animationStartedAt = performance.now();
  let lastFrameAt = performance.now();
  let fpsWindowStartedAt = performance.now();
  let fpsWindowFrames = 0;

  function asNumber(value, fallback) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function firstDefined() {
    for (let index = 0; index < arguments.length; index += 1) {
      if (arguments[index] !== undefined && arguments[index] !== null) {
        return arguments[index];
      }
    }
    return undefined;
  }

  function normalizeFileUrl(value) {
    if (typeof value !== "string") {
      throw new TypeError("Character package URL must be a string");
    }
    const trimmed = value.trim();
    if (/^[a-zA-Z]:[\\/]/.test(trimmed)) {
      return `file:///${trimmed.replace(/\\/g, "/")}`;
    }
    return trimmed;
  }

  function packageLocations(value) {
    const normalized = normalizeFileUrl(value);
    const supplied = new URL(normalized, document.baseURI);
    const isJson = /\.json$/i.test(supplied.pathname);
    const manifestUrl = isJson ? supplied : new URL("character.json", `${supplied.href.replace(/\/?$/, "/")}`);
    return { manifestUrl, baseUrl: new URL("./", manifestUrl) };
  }

  function resourceName(manifest, name, fallback) {
    const files = manifest.files || manifest.resources || {};
    const aliases = {
      atlas: ["atlas", "atlasUrl"],
      rig: ["rig", "rigUrl"],
      animations: ["animations", "animationsUrl"],
      skin: ["skin", "texture", "image", "skinUrl"]
    };
    for (const key of aliases[name]) {
      const candidate = firstDefined(files[key], manifest[key]);
      if (typeof candidate === "string" && candidate.trim()) {
        return candidate;
      }
    }
    return fallback;
  }

  async function fetchJson(url) {
    const response = await fetch(url.href, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Unable to load ${url.pathname}: HTTP ${response.status}`);
    }
    return response.json();
  }

  function loadImage(url) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error(`Unable to load image ${url.pathname}`));
      image.src = url.href;
    });
  }

  function entriesFrom(value, fallbackPrefix) {
    if (Array.isArray(value)) {
      return value.map((item, index) => [
        String(firstDefined(item && item.name, item && item.id, item && item.filename, `${fallbackPrefix}${index}`)),
        item || {}
      ]);
    }
    if (value && typeof value === "object") {
      return Object.entries(value);
    }
    return [];
  }

  function normalizeAtlas(atlas, image) {
    const source = firstDefined(atlas.frames, atlas.regions, atlas.sprites, atlas.parts, atlas);
    const regions = new Map();

    for (const [name, rawValue] of entriesFrom(source, "frame-")) {
      const raw = rawValue || {};
      const frame = firstDefined(raw.frame, raw.rect, raw.bounds, raw) || {};
      const sourceSize = firstDefined(raw.sourceSize, raw.originalSize, raw.size, {}) || {};
      const trim = firstDefined(raw.spriteSourceSize, raw.trim, raw.offset, {}) || {};
      const x = asNumber(firstDefined(frame.x, frame.left), 0);
      const y = asNumber(firstDefined(frame.y, frame.top), 0);
      const width = asNumber(firstDefined(frame.w, frame.width), 0);
      const height = asNumber(firstDefined(frame.h, frame.height), 0);
      if (width <= 0 || height <= 0) {
        continue;
      }

      const rotated = Boolean(raw.rotated || raw.rotate);
      const trimmedWidth = asNumber(firstDefined(trim.w, trim.width), rotated ? height : width);
      const trimmedHeight = asNumber(firstDefined(trim.h, trim.height), rotated ? width : height);
      const fullWidth = Math.max(1, asNumber(firstDefined(sourceSize.w, sourceSize.width), trimmedWidth));
      const fullHeight = Math.max(1, asNumber(firstDefined(sourceSize.h, sourceSize.height), trimmedHeight));
      const trimX = asNumber(firstDefined(trim.x, trim.left), 0);
      const trimY = asNumber(firstDefined(trim.y, trim.top), 0);
      const bitmap = document.createElement("canvas");
      bitmap.width = Math.ceil(fullWidth);
      bitmap.height = Math.ceil(fullHeight);
      const bitmapContext = bitmap.getContext("2d", { alpha: true });
      bitmapContext.imageSmoothingEnabled = true;

      if (rotated) {
        bitmapContext.save();
        bitmapContext.translate(trimX, trimY);
        bitmapContext.translate(0, width);
        bitmapContext.rotate(-Math.PI / 2);
        bitmapContext.drawImage(image, x, y, width, height, 0, 0, width, height);
        bitmapContext.restore();
      } else {
        bitmapContext.drawImage(image, x, y, width, height, trimX, trimY, trimmedWidth, trimmedHeight);
      }

      regions.set(name, {
        name,
        bitmap,
        width: fullWidth,
        height: fullHeight,
        pivot: raw.pivot || null
      });
    }
    return regions;
  }

  function nodeValue(raw, property, fallback) {
    const transform = raw.transform || {};
    return firstDefined(raw[property], transform[property], fallback);
  }

  function vectorValue(value, axis) {
    if (Array.isArray(value)) return value[axis === "x" ? 0 : 1];
    if (value && typeof value === "object") return value[axis];
    return undefined;
  }

  function normalizeNode(name, raw, kind, index) {
    const position = raw.position || {};
    const pivot = raw.pivot || raw.anchor || {};
    const scaleVector = nodeValue(raw, "scale", 1);
    const rawScale = asNumber(scaleVector, 1);
    const sprite = firstDefined(
      raw.region, raw.frame, raw.sprite, raw.attachment, raw.texture,
      kind === "part" || kind === "slot" ? name : null
    );
    return {
      id: String(firstDefined(raw.id, raw.name, name)),
      parentId: firstDefined(raw.parentId, raw.parent, raw.bone, raw.parentBone, null),
      sprite: sprite === null || sprite === undefined ? null : String(sprite),
      x: asNumber(firstDefined(nodeValue(raw, "x"), vectorValue(position, "x")), 0),
      y: asNumber(firstDefined(nodeValue(raw, "y"), vectorValue(position, "y")), 0),
      rotation: asNumber(firstDefined(nodeValue(raw, "rotation"), raw.angle), 0),
      scaleX: asNumber(firstDefined(nodeValue(raw, "scaleX"), vectorValue(scaleVector, "x")), rawScale),
      scaleY: asNumber(firstDefined(nodeValue(raw, "scaleY"), vectorValue(scaleVector, "y")), rawScale),
      opacity: asNumber(nodeValue(raw, "opacity", 1), 1),
      visible: nodeValue(raw, "visible", true) !== false,
      pivotX: asNumber(firstDefined(raw.pivotX, raw.anchorX, vectorValue(pivot, "x")), NaN),
      pivotY: asNumber(firstDefined(raw.pivotY, raw.anchorY, vectorValue(pivot, "y")), NaN),
      pivotNormalized: firstDefined(raw.pivotNormalized, raw.anchorNormalized, null),
      width: asNumber(raw.width, NaN),
      height: asNumber(raw.height, NaN),
      zIndex: asNumber(firstDefined(raw.zIndex, raw.z, raw.layer, raw.order), index),
      children: []
    };
  }

  function normalizeRig(rig) {
    const nodes = [];
    const hasBones = Array.isArray(rig.bones) || (rig.bones && typeof rig.bones === "object");
    const mainSource = firstDefined(rig.nodes, rig.parts, hasBones ? rig.bones : null, rig.layers, []);
    const kind = rig.parts ? "part" : (hasBones ? "bone" : "node");

    entriesFrom(mainSource, "node-").forEach(([name, raw], index) => {
      nodes.push(normalizeNode(name, raw, kind, index));
    });

    entriesFrom(rig.slots, "slot-").forEach(([name, raw], index) => {
      nodes.push(normalizeNode(name, raw, "slot", nodes.length + index));
    });

    const byId = new Map(nodes.map((node) => [node.id, node]));
    const roots = [];
    nodes.forEach((node) => {
      const parent = node.parentId === null || node.parentId === undefined
        ? null
        : byId.get(String(node.parentId));
      if (parent && parent !== node) {
        parent.children.push(node);
      } else {
        roots.push(node);
      }
    });
    const sortNodes = (items) => {
      items.sort((left, right) => left.zIndex - right.zIndex);
      items.forEach((item) => sortNodes(item.children));
    };
    sortNodes(roots);
    return { nodes, roots, byId };
  }

  function animationTimeUnit(animationData, clip, duration) {
    const unit = String(firstDefined(clip.timeUnit, animationData.timeUnit, "")).toLowerCase();
    if (unit.startsWith("s") && unit !== "ms") {
      return 1000;
    }
    if (unit === "frames" || unit === "frame") {
      return 1000 / Math.max(1, asNumber(firstDefined(clip.fps, animationData.fps), 60));
    }
    return !unit && duration > 0 && duration <= 60 ? 1000 : 1;
  }

  function normalizeKeyframes(value, durationMs, multiplier, fps) {
    let source = value;
    if (source && !Array.isArray(source) && typeof source === "object") {
      source = firstDefined(source.keyframes, source.frames, source.values, source);
    }
    if (!Array.isArray(source)) {
      return [{ time: 0, value: source }];
    }
    if (!source.length) {
      return [];
    }
    return source.map((entry, index) => {
      if (entry && typeof entry === "object" && !Array.isArray(entry)) {
        const frame = firstDefined(entry.frame, entry.index);
        let time = firstDefined(entry.timeMs, entry.time, entry.t);
        if (frame !== undefined) {
          time = asNumber(frame, 0) * 1000 / fps;
        } else if (entry.timeMs === undefined) {
          time = asNumber(time, index) * multiplier;
        }
        return {
          time: Math.max(0, asNumber(time, 0)),
          value: firstDefined(entry.value, entry.v, entry.val)
        };
      }
      const time = source.length === 1 ? 0 : durationMs * index / (source.length - 1);
      return { time, value: entry };
    }).sort((left, right) => left.time - right.time);
  }

  function addPropertyTrack(targetTracks, nodeId, property, value, durationMs, multiplier, fps) {
    const aliases = {
      "position.x": "x",
      "position.y": "y",
      "scale.x": "scaleX",
      "scale.y": "scaleY",
      alpha: "opacity"
    };
    property = aliases[property] || property;
    if (!ANIMATED_PROPERTIES.has(property)) {
      return;
    }
    if (!targetTracks[nodeId]) {
      targetTracks[nodeId] = {};
    }
    targetTracks[nodeId][property] = normalizeKeyframes(value, durationMs, multiplier, fps);
  }

  function normalizeTrackCollection(targetTracks, source, durationMs, multiplier, fps) {
    if (Array.isArray(source)) {
      source.forEach((track) => {
        if (!track || typeof track !== "object") return;
        const nodeId = String(firstDefined(track.target, track.node, track.bone, track.part, track.id, ""));
        const property = firstDefined(track.property, track.channel);
        if (nodeId && property) {
          addPropertyTrack(targetTracks, nodeId, property, firstDefined(track.keyframes, track.frames, track.values, track.value), durationMs, multiplier, fps);
        }
      });
      return;
    }
    entriesFrom(source, "").forEach(([nodeId, properties]) => {
      if (!properties || typeof properties !== "object") return;
      for (const [property, value] of Object.entries(properties)) {
        addPropertyTrack(targetTracks, String(nodeId), property, value, durationMs, multiplier, fps);
      }
    });
  }

  function normalizePoseFrames(targetTracks, frames, durationMs, multiplier, fps) {
    if (!Array.isArray(frames)) return;
    frames.forEach((frame, index) => {
      if (!frame || typeof frame !== "object") return;
      const frameIndex = firstDefined(frame.frame, frame.index);
      let time = firstDefined(frame.timeMs, frame.time, frame.t);
      if (frameIndex !== undefined) {
        time = asNumber(frameIndex, 0) * 1000 / fps;
      } else if (frame.timeMs === undefined && time !== undefined) {
        time = asNumber(time, 0) * multiplier;
      } else if (time === undefined) {
        time = frames.length === 1 ? 0 : durationMs * index / (frames.length - 1);
      }
      const pose = firstDefined(frame.nodes, frame.bones, frame.parts, frame.pose, {});
      entriesFrom(pose, "").forEach(([nodeId, properties]) => {
        for (const [property, value] of Object.entries(properties || {})) {
          if (!ANIMATED_PROPERTIES.has(property)) continue;
          if (!targetTracks[nodeId]) targetTracks[nodeId] = {};
          if (!targetTracks[nodeId][property]) targetTracks[nodeId][property] = [];
          targetTracks[nodeId][property].push({ time: asNumber(time, 0), value });
        }
      });
    });
    Object.values(targetTracks).forEach((properties) => {
      Object.values(properties).forEach((keys) => keys.sort((a, b) => a.time - b.time));
    });
  }

  function normalizeAnimations(animationData) {
    const source = firstDefined(animationData.animations, animationData.clips, animationData.states, animationData);
    const clips = new Map();
    entriesFrom(source, "animation-").forEach(([name, raw]) => {
      if (!raw || typeof raw !== "object") return;
      const fps = Math.max(1, asNumber(firstDefined(raw.fps, animationData.fps), 60));
      const rawDuration = asNumber(firstDefined(raw.durationMs, raw.duration, raw.length), 0);
      const multiplier = raw.durationMs !== undefined ? 1 : animationTimeUnit(animationData, raw, rawDuration);
      let durationMs = raw.durationMs !== undefined ? rawDuration : rawDuration * multiplier;
      if (!durationMs && raw.frameCount) durationMs = asNumber(raw.frameCount, 1) * 1000 / fps;
      const tracks = {};
      normalizeTrackCollection(tracks, firstDefined(raw.tracks, raw.nodes, raw.bones, raw.parts, {}), durationMs, multiplier, fps);
      normalizePoseFrames(tracks, raw.keyframes, durationMs, multiplier, fps);
      let latestKey = 0;
      Object.values(tracks).forEach((properties) => {
        Object.values(properties).forEach((keys) => {
          if (keys.length) latestKey = Math.max(latestKey, keys[keys.length - 1].time);
        });
      });
      durationMs = Math.max(1, durationMs || latestKey || 1000);
      clips.set(String(name), {
        name: String(name),
        durationMs,
        loop: raw.loop !== false,
        next: firstDefined(raw.next, raw.fallback, null),
        tracks
      });
    });
    return {
      clips,
      fallbacks: firstDefined(animationData.fallbacks, animationData.stateFallbacks, {}) || {},
      defaultState: firstDefined(animationData.defaultState, animationData.defaultAnimation, null)
    };
  }

  function selectAnimation(requestedState) {
    if (!scene) return null;
    const requested = String(requestedState || "idle");
    const stateMap = scene.manifest.stateMap || scene.manifest.animationStates || {};
    const manifestFallbacks = scene.manifest.stateFallbacks || scene.manifest.fallbacks || {};
    const candidates = [];
    const add = (value) => {
      if (typeof value === "string" && value && !candidates.includes(value)) candidates.push(value);
    };
    add(stateMap[requested]);
    add(requested);
    add(manifestFallbacks[requested]);
    add(scene.animations.fallbacks[requested]);
    add(scene.manifest.defaultAnimation);
    add(scene.manifest.defaultState);
    add(scene.animations.defaultState);
    add("idle");
    add(scene.animations.clips.keys().next().value);
    return candidates.find((name) => scene.animations.clips.has(name)) || null;
  }

  function parseBoolean(value) {
    if (typeof value === "string") {
      return !["false", "0", "off", "hidden"].includes(value.toLowerCase());
    }
    return Boolean(value);
  }

  function sampleTrack(keys, time, property) {
    if (!keys || !keys.length) return undefined;
    if (time <= keys[0].time) return keys[0].value;
    const last = keys[keys.length - 1];
    if (time >= last.time) return last.value;
    let rightIndex = 1;
    while (rightIndex < keys.length && keys[rightIndex].time < time) rightIndex += 1;
    const left = keys[rightIndex - 1];
    const right = keys[rightIndex];
    if (property === "visible") return parseBoolean(left.value);
    const leftValue = asNumber(left.value, 0);
    const rightValue = asNumber(right.value, leftValue);
    const span = Math.max(0.0001, right.time - left.time);
    const amount = (time - left.time) / span;
    return leftValue + (rightValue - leftValue) * amount;
  }

  function poseForNode(node, clip, time) {
    const pose = {
      x: node.x,
      y: node.y,
      rotation: node.rotation,
      scaleX: node.scaleX,
      scaleY: node.scaleY,
      opacity: node.opacity,
      visible: node.visible
    };
    const tracks = clip && clip.tracks[node.id];
    if (!tracks) return pose;
    let uniformScale;
    for (const [property, keys] of Object.entries(tracks)) {
      const value = sampleTrack(keys, time, property);
      if (value === undefined) continue;
      if (property === "scale") uniformScale = asNumber(value, 1);
      else if (property === "visible") pose.visible = parseBoolean(value);
      else if (NUMBER_PROPERTIES.has(property)) pose[property] = asNumber(value, pose[property]);
    }
    if (uniformScale !== undefined) {
      if (!tracks.scaleX) pose.scaleX = uniformScale;
      if (!tracks.scaleY) pose.scaleY = uniformScale;
    }
    return pose;
  }

  function pivotFor(node, region) {
    let x = node.pivotX;
    let y = node.pivotY;
    let normalized = node.pivotNormalized;
    if (!Number.isFinite(x) && region.pivot) x = asNumber(region.pivot.x, NaN);
    if (!Number.isFinite(y) && region.pivot) y = asNumber(region.pivot.y, NaN);
    if (normalized === null) {
      normalized = Number.isFinite(x) && Number.isFinite(y) && x >= 0 && x <= 1 && y >= 0 && y <= 1;
    }
    if (!Number.isFinite(x)) x = region.width / 2;
    else if (normalized) x *= region.width;
    if (!Number.isFinite(y)) y = region.height / 2;
    else if (normalized) y *= region.height;
    return { x, y };
  }

  function multiplyMatrix(parent, local) {
    return {
      a: parent.a * local.a + parent.c * local.b,
      b: parent.b * local.a + parent.d * local.b,
      c: parent.a * local.c + parent.c * local.d,
      d: parent.b * local.c + parent.d * local.d,
      e: parent.a * local.e + parent.c * local.f + parent.e,
      f: parent.b * local.e + parent.d * local.f + parent.f
    };
  }

  function collectDrawables(node, clip, time, rotationFactor, parentMatrix, parentOpacity, visited, drawables) {
    if (visited.has(node)) return;
    visited.add(node);
    const pose = poseForNode(node, clip, time);
    if (!pose.visible || pose.opacity <= 0) return;
    const angle = pose.rotation * rotationFactor;
    const cosine = Math.cos(angle);
    const sine = Math.sin(angle);
    const localMatrix = {
      a: cosine * pose.scaleX,
      b: sine * pose.scaleX,
      c: -sine * pose.scaleY,
      d: cosine * pose.scaleY,
      e: pose.x,
      f: pose.y
    };
    const worldMatrix = multiplyMatrix(parentMatrix, localMatrix);
    const opacity = parentOpacity * Math.max(0, Math.min(1, pose.opacity));
    const region = node.sprite ? scene.regions.get(node.sprite) : null;
    if (region) {
      drawables.push({ node, region, matrix: worldMatrix, opacity });
    }
    node.children.forEach((child) => {
      collectDrawables(child, clip, time, rotationFactor, worldMatrix, opacity, visited, drawables);
    });
  }

  function drawDrawable(drawable) {
    const { node, region, matrix, opacity } = drawable;
    const pivot = pivotFor(node, region);
    const width = Number.isFinite(node.width) ? node.width : region.width;
    const height = Number.isFinite(node.height) ? node.height : region.height;
    const ratioX = width / region.width;
    const ratioY = height / region.height;
    context.save();
    context.transform(matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f);
    context.globalAlpha *= opacity;
    context.drawImage(region.bitmap, -pivot.x * ratioX, -pivot.y * ratioY, width, height);
    context.restore();
  }

  function sceneTransform() {
    const manifestViewport = scene.manifest.canvas || scene.manifest.viewport || {};
    const rigViewport = scene.rigData.canvas || scene.rigData.viewport || {};
    const designWidth = asNumber(firstDefined(manifestViewport.width, rigViewport.width), 0);
    const designHeight = asNumber(firstDefined(manifestViewport.height, rigViewport.height), 0);
    const configuredScale = asNumber(firstDefined(scene.manifest.renderScale, scene.rigData.renderScale), 1);
    if (designWidth > 0 && designHeight > 0) {
      const scale = Math.min(status.canvasWidth / designWidth, status.canvasHeight / designHeight) * configuredScale;
      return {
        x: (status.canvasWidth - designWidth * scale) / 2,
        y: (status.canvasHeight - designHeight * scale) / 2,
        scale
      };
    }
    const origin = scene.manifest.origin || scene.rigData.origin || {};
    return {
      x: status.canvasWidth / 2 + asNumber(firstDefined(origin.x, scene.rigData.offsetX), 0),
      y: status.canvasHeight / 2 + asNumber(firstDefined(origin.y, scene.rigData.offsetY), 0),
      scale: configuredScale
    };
  }

  function resizeCanvas() {
    const width = Math.max(1, document.documentElement.clientWidth || window.innerWidth || 1);
    const height = Math.max(1, document.documentElement.clientHeight || window.innerHeight || 1);
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const pixelWidth = Math.round(width * dpr);
    const pixelHeight = Math.round(height * dpr);
    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
      canvas.width = pixelWidth;
      canvas.height = pixelHeight;
    }
    status.canvasWidth = width;
    status.canvasHeight = height;
    return dpr;
  }

  function currentClip(now) {
    if (!scene || !status.activeAnimation) return { clip: null, time: 0 };
    let clip = scene.animations.clips.get(status.activeAnimation);
    if (!clip) return { clip: null, time: 0 };
    let elapsed = Math.max(0, now - animationStartedAt);
    if (clip.loop) {
      elapsed %= clip.durationMs;
    } else if (elapsed >= clip.durationMs && clip.next && scene.animations.clips.has(String(clip.next))) {
      status.activeAnimation = String(clip.next);
      animationStartedAt = now;
      clip = scene.animations.clips.get(status.activeAnimation);
      elapsed = 0;
    } else {
      elapsed = Math.min(elapsed, clip.durationMs);
    }
    return { clip, time: elapsed };
  }

  function render(now) {
    const dpr = resizeCanvas();
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.imageSmoothingEnabled = true;

    if (scene && status.ready) {
      const animation = currentClip(now);
      const transform = sceneTransform();
      context.save();
      context.translate(transform.x, transform.y);
      context.scale(transform.scale, transform.scale);
      const unit = String(firstDefined(
        scene.animationData.rotationUnit,
        scene.rigData.rotationUnit,
        scene.manifest.rotationUnit,
        "degrees"
      )).toLowerCase();
      const rotationFactor = unit.startsWith("rad") ? 1 : Math.PI / 180;
      const visited = new Set();
      const drawables = [];
      const identity = { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 };
      scene.rig.roots.forEach((node) => {
        collectDrawables(node, animation.clip, animation.time, rotationFactor, identity, 1, visited, drawables);
      });
      drawables.sort((left, right) => left.node.zIndex - right.node.zIndex);
      drawables.forEach(drawDrawable);
      context.restore();
    }

    status.frameCount += 1;
    fpsWindowFrames += 1;
    if (now - fpsWindowStartedAt >= 500) {
      status.measuredFps = Math.round(fpsWindowFrames * 1000 / (now - fpsWindowStartedAt));
      fpsWindowFrames = 0;
      fpsWindowStartedAt = now;
    }
    lastFrameAt = now;
    requestAnimationFrame(render);
  }

  async function loadCharacterPackage(url) {
    const version = ++loadVersion;
    status.loading = true;
    status.ready = false;
    status.error = null;
    try {
      const locations = packageLocations(url);
      const manifest = await fetchJson(locations.manifestUrl);
      const atlasUrl = new URL(resourceName(manifest, "atlas", "atlas.json"), locations.baseUrl);
      const rigUrl = new URL(resourceName(manifest, "rig", "rig.json"), locations.baseUrl);
      const animationsUrl = new URL(resourceName(manifest, "animations", "animations.json"), locations.baseUrl);
      const skinUrl = new URL(resourceName(manifest, "skin", "skin.png"), locations.baseUrl);
      const [atlasData, rigData, animationData, skin] = await Promise.all([
        fetchJson(atlasUrl), fetchJson(rigUrl), fetchJson(animationsUrl), loadImage(skinUrl)
      ]);
      if (version !== loadVersion) return getRendererStatus();

      const rig = normalizeRig(rigData);
      const animations = normalizeAnimations(animationData);
      scene = {
        manifest,
        atlasData,
        rigData,
        animationData,
        skin,
        regions: normalizeAtlas(atlasData, skin),
        rig,
        animations
      };
      status.packageUrl = locations.manifestUrl.href;
      status.partCount = rig.nodes.length;
      status.loading = false;
      status.ready = true;
      status.error = null;
      const selected = selectAnimation(status.requestedState);
      status.activeAnimation = selected;
      animationStartedAt = performance.now();
      document.documentElement.dataset.rendererStatus = "ready";
      window.dispatchEvent(new CustomEvent("characterpackageloaded", { detail: getRendererStatus() }));
      if (window.pythonBridge && typeof window.pythonBridge.sendEvent === "function") {
        window.pythonBridge.sendEvent("renderer-ready", getRendererStatus());
      }
      return getRendererStatus();
    } catch (error) {
      if (version !== loadVersion) return getRendererStatus();
      scene = null;
      status.loading = false;
      status.ready = false;
      status.activeAnimation = null;
      status.partCount = 0;
      status.error = error instanceof Error ? error.message : String(error);
      document.documentElement.dataset.rendererStatus = "error";
      window.dispatchEvent(new CustomEvent("renderererror", { detail: getRendererStatus() }));
      if (window.pythonBridge && typeof window.pythonBridge.sendEvent === "function") {
        window.pythonBridge.sendEvent("renderer-error", { message: status.error });
      }
      throw error;
    }
  }

  function setAnimationState(state) {
    const nextState = typeof state === "object" && state !== null
      ? firstDefined(state.state, state.name, state.animation)
      : state;
    status.requestedState = String(nextState || "idle");
    const selected = selectAnimation(status.requestedState);
    if (selected !== status.activeAnimation) {
      status.activeAnimation = selected;
      animationStartedAt = performance.now();
    }
    return status.activeAnimation;
  }

  function getRendererStatus() {
    return { ...status };
  }

  function packageUrlFromSignal(args) {
    const values = Array.from(args);
    for (let index = values.length - 1; index >= 0; index -= 1) {
      let value = values[index];
      if (typeof value === "string" && value.trim().startsWith("{")) {
        try { value = JSON.parse(value); } catch (_) { /* Use the original value. */ }
      }
      if (value && typeof value === "object") {
        const metadata = value.metadata && typeof value.metadata === "object" ? value.metadata : {};
        const direct = firstDefined(
          value.url, value.packageUrl, value.manifestUrl, value.path, value.characterUrl,
          value.directory, value.root, value.baseUrl, metadata.packageUrl, metadata.root
        );
        if (typeof direct === "string" && direct.trim()) return direct;
        if (typeof value.skin === "string" && value.skin.trim()) {
          try {
            return new URL("./", new URL(normalizeFileUrl(value.skin), document.baseURI)).href;
          } catch (_) {
            // Continue looking for another signal argument.
          }
        }
        value = null;
      }
      if (typeof value === "string" && value.trim()) return value;
    }
    return null;
  }

  function connectSignal(signal, handler) {
    if (signal && typeof signal.connect === "function") {
      signal.connect(handler);
      return true;
    }
    return false;
  }

  function initializeBridge() {
    if (!window.qt || !window.qt.webChannelTransport || typeof window.QWebChannel !== "function") {
      return;
    }
    new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
      const objects = channel.objects || {};
      const bridge = objects.bridge || objects.petBridge || objects.webBridge || Object.values(objects)[0];
      if (!bridge) return;
      window.pythonBridge = bridge;
      connectSignal(bridge.stateChanged, function () {
        const values = Array.from(arguments);
        const state = values.find((value) => typeof value === "string" || (value && typeof value === "object"));
        if (state !== undefined) setAnimationState(state);
      });
      connectSignal(bridge.characterChanged, function () {
        const url = packageUrlFromSignal(arguments);
        if (url) loadCharacterPackage(url).catch(() => {});
      });

      const initialState = firstDefined(bridge.currentState, bridge.state, bridge.animationState);
      if (typeof initialState === "string" && initialState) setAnimationState(initialState);
      const initialUrl = firstDefined(bridge.characterPackageUrl, bridge.characterUrl, bridge.packageUrl);
      if (typeof initialUrl === "string" && initialUrl) loadCharacterPackage(initialUrl).catch(() => {});
      if (typeof bridge.snapshot === "function") {
        bridge.snapshot((snapshot) => {
          if (!snapshot || typeof snapshot !== "object") return;
          if (snapshot.state) setAnimationState(snapshot.state);
          const snapshotUrl = packageUrlFromSignal([snapshot.character]);
          if (snapshotUrl) loadCharacterPackage(snapshotUrl).catch(() => {});
        });
      }
      if (typeof bridge.ready === "function") bridge.ready();
      window.dispatchEvent(new CustomEvent("webchannelready", { detail: { bridge } }));
    });
  }

  window.loadCharacterPackage = loadCharacterPackage;
  window.setAnimationState = setAnimationState;
  window.getRendererStatus = getRendererStatus;

  window.addEventListener("resize", resizeCanvas);
  document.documentElement.dataset.rendererStatus = "empty";
  resizeCanvas();
  requestAnimationFrame(render);
  initializeBridge();
}());
