"use strict";

/*
 * Timeline shared by the Extract page and the Editor.
 *
 * The overview shows the whole video: a ruler, the subtitle cues as blocks, the
 * playhead and (on Extract) the IN/OUT range that OCR will read. The page's
 * existing seek slider is laid invisibly over the overview track, so scrubbing
 * keeps using the same code path as before.
 *
 * The Editor also gets a detail strip: a short window around the playhead in
 * which each cue is a labelled block that can be clicked to select it.
 */
window.SubtitleYCTimeline = (() => {
  const TICK_STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 14400];
  const DETAIL_WINDOW_SECONDS = 20;

  function clock(seconds) {
    const total = Math.max(0, Math.round(Number(seconds) || 0));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    const tail = `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    return hours > 0 ? `${hours}:${tail}` : tail;
  }

  function node(tag, className) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    return element;
  }

  function tickStep(span, width, minGap) {
    const maxTicks = Math.max(2, Math.floor(width / minGap));
    return TICK_STEPS.find((step) => span / step <= maxTicks) || TICK_STEPS[TICK_STEPS.length - 1];
  }

  function plainText(text) {
    return String(text || "").replace(/<\/?(?:b|i|u|font)\b[^>]*>/gi, "").replace(/\s+/g, " ").trim();
  }

  function create(options) {
    const root = options.root;
    const slider = options.slider;
    if (!root || !slider) return { render() {}, update() {} };

    const ruler = root.querySelector(".tl-ruler");
    const track = root.querySelector(".tl-track");
    const canvas = node("canvas", "tl-canvas");
    const shadeStart = node("div", "tl-shade");
    const shadeEnd = node("div", "tl-shade");
    const windowBand = node("div", "tl-window");
    const playhead = node("div", "tl-playhead");
    track.prepend(canvas, shadeStart, shadeEnd, windowBand);
    root.append(playhead);
    shadeStart.hidden = true;
    shadeEnd.hidden = true;
    windowBand.hidden = true;

    const duration = () => Math.max(0, Number(options.duration?.() || 0));
    const time = () => Math.max(0, Number(options.time?.() || 0));
    const cues = () => options.cues?.() || [];
    const selected = () => Number(options.selected?.() ?? -1);

    let markerIn = null;
    let markerOut = null;
    if (options.range) {
      markerIn = node("button", "tl-marker tl-in");
      markerOut = node("button", "tl-marker tl-out");
      for (const [marker, label, name] of [[markerIn, "IN", "OCR range start"], [markerOut, "OUT", "OCR range end"]]) {
        marker.type = "button";
        marker.dataset.label = label;
        marker.setAttribute("aria-label", name);
        marker.title = name;
        marker.dataset.i18nSkip = "";
        track.append(marker);
      }
      bindMarker(markerIn, "start");
      bindMarker(markerOut, "end");
    }

    let detail = null;
    let detailRuler = null;
    let detailTrack = null;
    let detailPlayhead = null;
    let detailStart = -1;
    let dragging = false;
    if (options.detail) {
      detail = node("div", "tl-detail");
      detailRuler = node("div", "tl-ruler");
      detailTrack = node("div", "tl-detail-track");
      detailPlayhead = node("div", "tl-playhead");
      detail.append(detailRuler, detailTrack, detailPlayhead);
      root.append(detail);
      bindRetime();
      // The ruler above the strip seeks too, so the whole height of the playhead is clickable.
      detail.addEventListener("click", (event) => {
        if (suppressClick) {
          suppressClick = false;
          return;
        }
        const block = event.target.closest(".tl-block");
        if (block) {
          options.onSelectCue?.(Number(block.dataset.index));
          return;
        }
        const total = duration();
        if (!total) return;
        const bounds = detailTrack.getBoundingClientRect();
        const fraction = Math.max(0, Math.min(1, (event.clientX - bounds.left) / Math.max(1, bounds.width)));
        options.onSeek?.(detailStart + fraction * detailLength());
      });
    }

    // Drag either edge of the selected cue in the detail strip to retime it. The block is
    // resized in place while dragging and the change is committed once, on release.
    let suppressClick = false;
    function bindRetime() {
      detailTrack.addEventListener("pointerdown", (event) => {
        const block = event.target.closest('.tl-block[aria-current="true"]');
        if (!block || event.button !== 0 || !options.onRetime) return;
        const rect = block.getBoundingClientRect();
        const boundary = Math.abs(event.clientX - rect.left) <= 8 ? "start" : Math.abs(event.clientX - rect.right) <= 8 ? "end" : null;
        if (!boundary) return;
        event.preventDefault();
        const index = Number(block.dataset.index);
        const cue = cues()[index];
        const frame = Math.max(0.001, Number(options.frameSeconds?.() || 1 / 24));
        const original = boundary === "start" ? Number(cue.start_seconds) : Number(cue.end_seconds);
        const length = detailLength();
        const windowStart = detailStart;
        const bounds = detailTrack.getBoundingClientRect();
        const tip = node("div", "drag-tip");
        tip.dataset.i18nSkip = "";
        detailTrack.append(tip);
        let next = original;
        dragging = true;
        detailTrack.setPointerCapture?.(event.pointerId);
        const move = (moveEvent) => {
          const raw = windowStart + Math.max(0, Math.min(1, (moveEvent.clientX - bounds.left) / Math.max(1, bounds.width))) * length;
          const snapped = Math.round(raw / frame) * frame;
          next = boundary === "start"
            ? Math.max(0, Math.min(Number(cue.end_seconds) - frame, snapped))
            : Math.min(duration(), Math.max(Number(cue.start_seconds) + frame, snapped));
          const start = boundary === "start" ? next : Number(cue.start_seconds);
          const end = boundary === "end" ? next : Number(cue.end_seconds);
          block.style.left = `${Math.max(0, ((start - windowStart) / length) * 100)}%`;
          block.style.width = `${((Math.min(end, windowStart + length) - Math.max(start, windowStart)) / length) * 100}%`;
          const frames = Math.round((next - original) / frame);
          const clockText = options.formatTime ? options.formatTime(next) : clock(next);
          tip.textContent = `${clockText}  (${frames > 0 ? "+" : ""}${frames})`;
          tip.style.left = `${((next - windowStart) / length) * 100}%`;
          options.onRetimePreview?.(boundary, next);
        };
        const stop = () => {
          detailTrack.releasePointerCapture?.(event.pointerId);
          detailTrack.removeEventListener("pointermove", move);
          detailTrack.removeEventListener("pointerup", stop);
          detailTrack.removeEventListener("pointercancel", stop);
          tip.remove();
          dragging = false;
          suppressClick = true;
          window.setTimeout(() => { suppressClick = false; }, 0);
          if (Math.abs(next - original) > 1e-6) options.onRetime(index, boundary, next);
          else render();
        };
        detailTrack.addEventListener("pointermove", move);
        detailTrack.addEventListener("pointerup", stop);
        detailTrack.addEventListener("pointercancel", stop);
      });
    }

    function rangeValues() {
      const total = duration();
      const value = options.range?.() || {};
      const start = Math.max(0, Math.min(total, Number(value.start || 0)));
      const rawEnd = value.end === null || value.end === undefined || value.end === "" ? total : Number(value.end);
      const end = Math.max(start, Math.min(total, Number.isFinite(rawEnd) && rawEnd > 0 ? rawEnd : total));
      return { start, end };
    }

    function bindMarker(marker, boundary) {
      const move = (clientX) => {
        const total = duration();
        if (!total) return;
        const bounds = track.getBoundingClientRect();
        const fraction = Math.max(0, Math.min(1, (clientX - bounds.left) / Math.max(1, bounds.width)));
        applyBoundary(boundary, fraction * total);
      };
      marker.addEventListener("pointerdown", (event) => {
        if (event.button !== 0 || !duration()) return;
        event.preventDefault();
        marker.setPointerCapture?.(event.pointerId);
        const onMove = (moveEvent) => move(moveEvent.clientX);
        const stop = () => {
          marker.releasePointerCapture?.(event.pointerId);
          marker.removeEventListener("pointermove", onMove);
          marker.removeEventListener("pointerup", stop);
          marker.removeEventListener("pointercancel", stop);
        };
        marker.addEventListener("pointermove", onMove);
        marker.addEventListener("pointerup", stop);
        marker.addEventListener("pointercancel", stop);
      });
      marker.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();
        event.stopPropagation();
        const step = (event.shiftKey ? 10 : 1) * (event.key === "ArrowLeft" ? -1 : 1);
        const current = rangeValues();
        applyBoundary(boundary, (boundary === "start" ? current.start : current.end) + step);
      });
    }

    function applyBoundary(boundary, seconds) {
      const total = duration();
      const current = rangeValues();
      const minimumGap = Math.min(total, 0.5);
      if (boundary === "start") {
        const start = Math.max(0, Math.min(current.end - minimumGap, seconds));
        options.onRangeChange?.(start, current.end >= total ? null : current.end);
      } else {
        const end = Math.max(current.start + minimumGap, Math.min(total, seconds));
        options.onRangeChange?.(current.start, end >= total ? null : end);
      }
      renderRange();
    }

    function renderRuler(target, start, span, minGap) {
      target.replaceChildren();
      if (!span) return;
      const width = target.clientWidth || 1;
      const step = tickStep(span, width, minGap);
      const first = Math.ceil(start / step) * step;
      for (let value = first; value < start + span; value += step) {
        const tick = node("span");
        tick.dataset.i18nSkip = "";
        tick.textContent = clock(value);
        tick.style.left = `${((value - start) / span) * 100}%`;
        target.append(tick);
      }
    }

    function renderOverview() {
      const total = duration();
      const width = Math.max(1, track.clientWidth);
      const height = Math.max(1, track.clientHeight);
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      const context = canvas.getContext("2d");
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      root.classList.toggle("is-empty", !total);
      renderRuler(ruler, 0, total, 78);
      if (!total) return;
      const styles = getComputedStyle(root);
      const blockColor = styles.getPropertyValue("--tl-block").trim() || "#1f5a54";
      const lineColor = styles.getPropertyValue("--tl-block-line").trim() || "#2f8c82";
      const currentColor = styles.getPropertyValue("--accent-strong").trim() || "#2dd4bf";
      const warmColor = styles.getPropertyValue("--warm").trim() || "#fbbf24";
      const active = selected();
      cues().forEach((cue, index) => {
        const start = Number(cue.start_seconds || 0);
        const end = Number(cue.end_seconds || 0);
        const x = (start / total) * width;
        const blockWidth = Math.max(1, ((end - start) / total) * width);
        context.fillStyle = index === active ? currentColor : options.flagged?.(cue, index) ? warmColor : blockColor;
        context.fillRect(x, 6, blockWidth, height - 12);
        if (blockWidth >= 4 && index !== active) {
          context.fillStyle = lineColor;
          context.fillRect(x, 6, 1, height - 12);
        }
      });
    }

    function renderRange() {
      if (!options.range) return;
      const total = duration();
      const visible = total > 0;
      for (const element of [shadeStart, shadeEnd, markerIn, markerOut]) element.hidden = !visible;
      if (!visible) return;
      const { start, end } = rangeValues();
      const startPercent = (start / total) * 100;
      const endPercent = (end / total) * 100;
      shadeStart.style.left = "0";
      shadeStart.style.width = `${startPercent}%`;
      shadeEnd.style.left = `${endPercent}%`;
      shadeEnd.style.right = "0";
      markerIn.style.left = `${startPercent}%`;
      markerOut.style.left = `${endPercent}%`;
    }

    function detailLength() {
      return Math.min(DETAIL_WINDOW_SECONDS, duration()) || DETAIL_WINDOW_SECONDS;
    }

    function detailStartFor(seconds) {
      const length = detailLength();
      const total = duration();
      const page = Math.floor(seconds / length) * length;
      return Math.max(0, Math.min(Math.max(0, total - length), page));
    }

    function renderDetail() {
      if (!detail || dragging) return;
      const total = duration();
      detail.hidden = !total;
      windowBand.hidden = !total;
      if (!total) return;
      const length = detailLength();
      detailStart = detailStartFor(time());
      renderRuler(detailRuler, detailStart, length, 70);
      windowBand.style.left = `${(detailStart / total) * 100}%`;
      windowBand.style.width = `${(length / total) * 100}%`;
      detailTrack.replaceChildren();
      const active = selected();
      cues().forEach((cue, index) => {
        const start = Number(cue.start_seconds || 0);
        const end = Number(cue.end_seconds || 0);
        if (end <= detailStart || start >= detailStart + length) return;
        const block = node("button", "tl-block");
        block.type = "button";
        block.dataset.index = String(index);
        block.dataset.i18nSkip = "";
        block.textContent = plainText(cue.text);
        block.title = block.textContent;
        block.tabIndex = -1;
        block.style.left = `${Math.max(0, ((start - detailStart) / length) * 100)}%`;
        block.style.width = `${((Math.min(end, detailStart + length) - Math.max(start, detailStart)) / length) * 100}%`;
        if (index === active) block.setAttribute("aria-current", "true");
        if (options.flagged?.(cue, index)) block.classList.add("is-flagged");
        detailTrack.append(block);
      });
    }

    function update() {
      const total = duration();
      playhead.hidden = !total;
      if (detailPlayhead) detailPlayhead.hidden = !total;
      if (!total) return;
      const current = Math.min(total, time());
      playhead.style.left = `${(current / total) * 100}%`;
      if (!detail) return;
      if (!dragging && detailStartFor(current) !== detailStart) renderDetail();
      detailPlayhead.style.left = `${Math.max(0, Math.min(100, ((current - detailStart) / detailLength()) * 100))}%`;
    }

    function render() {
      renderOverview();
      renderRange();
      renderDetail();
      update();
    }

    if (typeof ResizeObserver === "function") new ResizeObserver(() => render()).observe(root);
    render();
    return { render, update, renderRange };
  }

  return { create, clock };
})();
