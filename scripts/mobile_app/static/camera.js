/* ════════════════════════════════════════════
   CAMERA UTILS — Apenas lógica de hardware
════════════════════════════════════════════ */
window._stream = null;
window._rafId  = null;

function stopCamera() {
  if (window._stream) {
    window._stream.getTracks().forEach(t => t.stop());
    window._stream = null;
  }
  if (window._rafId) {
    cancelAnimationFrame(window._rafId);
    window._rafId = null;
  }
}

async function startCamera(videoEl) {
  stopCamera();
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error("HTTPS necessário para acessar a câmera.");
  }
  window._stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: 'environment' } },
    audio: false,
  });
  videoEl.srcObject = window._stream;
  await videoEl.play();
}

function captureFrame(videoEl) {
  const c = document.createElement('canvas');
  const maxW = 1280;
  const scale = Math.min(1, maxW / videoEl.videoWidth);
  c.width  = videoEl.videoWidth * scale;
  c.height = videoEl.videoHeight * scale;
  c.getContext('2d').drawImage(videoEl, 0, 0, c.width, c.height);
  return c.toDataURL('image/jpeg', 0.85);
}

function downloadFallback(dataUrl, name) {
  const link = document.createElement('a');
  link.href = dataUrl;
  link.download = name;
  link.click();
}
