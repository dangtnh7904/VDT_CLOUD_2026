/**
 * Input validators for rbd-console.
 *
 * Guards against pool/image/path injection by validating against
 * configured allowlists before any SSH command is built.
 */

/** Characters allowed in image names (alphanumeric, dash, underscore, dot). */
const SAFE_NAME_RE = /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/;

/** Characters that must never appear in shell arguments. */
const SHELL_META_RE = /[;&|`$(){}[\]<>!\\'"*?\n\r]/;

export function csvSet(value) {
  return new Set(String(value || "").split(",").map(item => item.trim()).filter(Boolean));
}

/**
 * Validate that pool is in the allowlist.
 * @param {string} pool
 * @returns {{ok: boolean, error?: string}}
 */
export function validatePool(pool) {
  const allowed = [...csvSet(process.env.RBD_ALLOWED_POOLS || process.env.RBD_POOL)];
  if (!pool || typeof pool !== "string") {
    return { ok: false, error: "Pool name is required" };
  }
  if (!allowed.includes(pool)) {
    return { ok: false, error: `Pool "${pool}" not in allowlist: [${allowed.join(", ")}]` };
  }
  return { ok: true };
}

export function validateNamespace(namespace = "") {
  if (typeof namespace !== "string" || SHELL_META_RE.test(namespace)) {
    return { ok: false, error: "Namespace contains invalid characters" };
  }
  const allowed = csvSet(process.env.RBD_ALLOWED_NAMESPACES || "default");
  const normalized = namespace === "default" ? "" : namespace;
  const configured = new Set([...allowed].map(item => item === "default" ? "" : item));
  if (!configured.has(normalized)) {
    return { ok: false, error: `Namespace "${namespace}" is outside the allowlist` };
  }
  return { ok: true, value: normalized };
}

export function validateUuid(value, field = "value") {
  if (typeof value !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)) {
    return { ok: false, error: `${field} must be a UUID` };
  }
  return { ok: true, value: value.toLowerCase() };
}

/**
 * Validate image name against prefix and safe character rules.
 * @param {string} name
 * @returns {{ok: boolean, error?: string}}
 */
export function validateImageName(name) {
  if (!name || typeof name !== "string") {
    return { ok: false, error: "Image name is required" };
  }
  if (!SAFE_NAME_RE.test(name)) {
    return { ok: false, error: `Image name "${name}" contains invalid characters` };
  }
  if (SHELL_META_RE.test(name)) {
    return { ok: false, error: `Image name "${name}" contains shell metacharacters` };
  }
  const prefix = process.env.RBD_IMAGE_PREFIX || "";
  if (prefix && !name.startsWith(prefix)) {
    return { ok: false, error: `Image name must start with prefix "${prefix}"` };
  }
  return { ok: true };
}

/**
 * Validate that a path is safely under the mount root.
 * Rejects .., absolute paths outside root, and shell metacharacters.
 * @param {string} path
 * @returns {{ok: boolean, resolved?: string, error?: string}}
 */
export function validateMountPath(path) {
  const mountRoot = process.env.RBD_MOUNT_ROOT || "/mnt/rbd";
  if (!path || typeof path !== "string") {
    return { ok: false, error: "Path is required" };
  }
  if (SHELL_META_RE.test(path)) {
    return { ok: false, error: "Path contains shell metacharacters" };
  }

  // Normalize and check containment
  const segments = path.split("/").filter(Boolean);
  if (segments.includes("..") || segments.includes(".")) {
    return { ok: false, error: "Path traversal (..) not allowed" };
  }

  const resolved = mountRoot.replace(/\/+$/, "") + "/" + segments.join("/");

  if (resolved !== mountRoot && !resolved.startsWith(`${mountRoot.replace(/\/+$/, "")}/`)) {
    return { ok: false, error: `Path escapes mount root ${mountRoot}` };
  }

  return { ok: true, resolved };
}

/**
 * Validate a file path within a mounted volume.
 * @param {string} imageName - The image/volume name
 * @param {string} filePath - The relative file path within the volume
 * @returns {{ok: boolean, resolved?: string, error?: string}}
 */
export function validateFilePath(imageName, filePath) {
  const imgCheck = validateImageName(imageName);
  if (!imgCheck.ok) return imgCheck;

  const mountRoot = process.env.RBD_MOUNT_ROOT || "/mnt/rbd";
  const volumeRoot = `${mountRoot.replace(/\/+$/, "")}/${imageName}`;

  if (!filePath || typeof filePath !== "string") {
    return { ok: true, resolved: volumeRoot };
  }

  const segments = filePath.split("/").filter(Boolean);
  if (segments.includes("..") || segments.includes(".")) {
    return { ok: false, error: "Path traversal (..) not allowed" };
  }
  if (SHELL_META_RE.test(filePath)) {
    return { ok: false, error: "Path contains shell metacharacters" };
  }

  const resolved = volumeRoot + "/" + segments.join("/");
  if (resolved !== volumeRoot && !resolved.startsWith(`${volumeRoot}/`)) {
    return { ok: false, error: `Path escapes volume root ${volumeRoot}` };
  }

  return { ok: true, resolved };
}

/**
 * Build a safe shell command from parts (no string concatenation of user input).
 * Each argument is validated for shell metacharacters.
 * @param {string[]} parts
 * @returns {string}
 */
export function safeCommand(parts) {
  for (const part of parts) {
    if (typeof part !== "string" || !part || SHELL_META_RE.test(part) || /\s/.test(part)) {
      throw new Error(`Unsafe shell argument: ${part}`);
    }
  }
  return parts.join(" ");
}
