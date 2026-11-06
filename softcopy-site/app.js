// Decrypts docs/enc/<token>.bin in the browser. Nothing is sent anywhere except the
// fetch of the encrypted file; the ID and the #k= secret never leave the device.
(() => {
  "use strict";

  const MAGIC = "REQ1";
  const SEP = "\x1f";                       // must match encrypt_images.py
  const HEADER_LEN = 4 + 4 + 16 + 12;       // magic | iterations | salt | iv
  const MAX_ITER = 5_000_000;
  const ALLOWED_MIME = new Set(["image/png", "image/jpeg", "image/webp"]);
  const EXT = { "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp" };

  const $ = (id) => document.getElementById(id);
  const form = $("form"), input = $("uid"), go = $("go"), msg = $("msg");

  const token = new URLSearchParams(location.search).get("f") || "";
  const qrSecret = new URLSearchParams(location.hash.slice(1)).get("k") || "";

  function say(text, isError = false) {
    msg.textContent = text;
    msg.classList.toggle("error", isError);
  }

  // Must stay identical to normalize_id() in tools/encrypt_images.py
  function normalizeId(raw) {
    return raw.normalize("NFKC").replace(/[\s\-]+/g, "").toUpperCase();
  }

  if (!/^[A-Za-z0-9_-]{8,64}$/.test(token)) {
    form.hidden = true;
    say("This link is incomplete. Scan the QR code on your card again.", true);
    return;
  }
  if (!window.crypto || !crypto.subtle) {
    form.hidden = true;
    say("This browser can't decrypt the card. Open the link in Chrome or Safari.", true);
    return;
  }

  let blobPromise = null;  // fetch once, retry decrypt with different IDs
  function fetchBlob() {
    blobPromise ??= fetch(`enc/${token}.bin`, { cache: "no-cache" }).then((r) => {
      if (!r.ok) throw new Error(r.status === 404 ? "notfound" : "network");
      return r.arrayBuffer();
    }).catch((e) => { blobPromise = null; throw e; });
    return blobPromise;
  }

  async function decrypt(buf, id) {
    if (buf.byteLength < HEADER_LEN + 16) throw new Error("corrupt");
    const header = new Uint8Array(buf, 0, HEADER_LEN);
    if (new TextDecoder().decode(header.subarray(0, 4)) !== MAGIC) throw new Error("corrupt");
    const iterations = new DataView(buf, 4, 4).getUint32(0, false);
    if (iterations < 1000 || iterations > MAX_ITER) throw new Error("corrupt");
    const salt = header.slice(8, 24);
    const iv = header.slice(24, 36);
    const ct = new Uint8Array(buf, HEADER_LEN);

    const pw = normalizeId(id) + (qrSecret ? SEP + qrSecret : "");
    const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(pw), "PBKDF2", false, ["deriveKey"]);
    const key = await crypto.subtle.deriveKey(
      { name: "PBKDF2", hash: "SHA-256", salt, iterations },
      base, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);

    let pt;
    try {
      pt = new Uint8Array(await crypto.subtle.decrypt({ name: "AES-GCM", iv, additionalData: header }, key, ct));
    } catch {
      throw new Error("wrongid");  // GCM tag mismatch = wrong ID (or tampered file)
    }
    const mimeLen = pt[0];
    const mime = new TextDecoder().decode(pt.subarray(1, 1 + mimeLen));
    if (!ALLOWED_MIME.has(mime)) throw new Error("corrupt");
    return new Blob([pt.subarray(1 + mimeLen)], { type: mime });
  }

  function show(blob) {
    const url = URL.createObjectURL(blob);
    const name = `my-card.${EXT[blob.type]}`;
    $("img").src = url;
    $("download").href = url;
    $("download").download = name;
    $("unlock").hidden = true;
    $("result").hidden = false;
    document.querySelector("p.sub").textContent = "Here's your soft copy.";

    const file = new File([blob], name, { type: blob.type });
    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      const share = $("share");
      share.hidden = false;
      share.onclick = () => navigator.share({ files: [file] }).catch(() => {});
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = input.value.trim();
    if (!id) return;
    go.disabled = true;
    say("Unlocking…");
    try {
      const buf = await fetchBlob();
      show(await decrypt(buf, id));
      say("");
    } catch (err) {
      const text = {
        wrongid: "That ID doesn't match this card. Check it and try again.",
        notfound: "We couldn't find this card. It may not be published yet.",
        network: "Couldn't reach the server. Check your connection and retry.",
        corrupt: "This card file is damaged. Please contact the event team.",
      }[err.message] || "Something went wrong. Please try again.";
      say(text, true);
      input.select();
    } finally {
      go.disabled = false;
    }
  });
})();
