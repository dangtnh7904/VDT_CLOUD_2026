import { createHash, randomUUID } from "crypto";
import { posix } from "path";
import { Transform, Writable } from "stream";
import { pipeline } from "stream/promises";
import { ExecutorError } from "./errors.js";

const MAX_PATH_BYTES = 4096;
const MAX_SEGMENT_BYTES = 255;
const SNIFF_BYTES = 4096;

function ensure(condition, code, message, options) {
  if (!condition) throw new ExecutorError(code, message, options);
}

function sftpCall(sftp, method, ...args) {
  return new Promise((resolve, reject) => {
    sftp[method](...args, (error, ...values) => {
      if (error) reject(error);
      else resolve(values.length > 1 ? values : values[0]);
    });
  });
}

function isNotFound(error) {
  return error?.code === 2 || error?.code === "ENOENT";
}

async function lstatOrNull(sftp, path) {
  try { return await sftpCall(sftp, "lstat", path); }
  catch (error) { if (isNotFound(error)) return null; throw error; }
}

function isWithin(root, candidate) {
  return candidate === root || candidate.startsWith(`${root}/`);
}

function fileType(attrs) {
  if (attrs?.isDirectory?.()) return "directory";
  if (attrs?.isFile?.()) return "file";
  if (attrs?.isSymbolicLink?.()) return "symlink";
  return "other";
}

function timestamp(seconds) {
  return Number.isFinite(seconds) && seconds > 0 ? new Date(seconds * 1000).toISOString() : null;
}

export function normalizeVolumePath(value = "/") {
  ensure(typeof value === "string", "INVALID_PATH", "File path must be a string");
  ensure(!/[\0\\]/.test(value) && !/[\u0001-\u001f\u007f]/.test(value), "INVALID_PATH", "File path contains unsupported characters");
  ensure(Buffer.byteLength(value) <= MAX_PATH_BYTES, "INVALID_PATH", "File path is too long");
  const rawSegments = value.split("/");
  ensure(!rawSegments.some(segment => segment === "." || segment === ".."), "PATH_ESCAPE", "Path traversal is not allowed");
  const segments = rawSegments.filter(Boolean);
  ensure(segments.every(segment => Buffer.byteLength(segment) <= MAX_SEGMENT_BYTES), "INVALID_PATH", "A file path segment is too long");
  return { logical: segments.length ? `/${segments.join("/")}` : "/", segments };
}

export function sniffMime(name, head = Buffer.alloc(0)) {
  const data = Buffer.from(head);
  if (data.length >= 8 && data.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) return "image/png";
  if (data.length >= 3 && data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff) return "image/jpeg";
  if (data.subarray(0, 6).toString("ascii") === "GIF87a" || data.subarray(0, 6).toString("ascii") === "GIF89a") return "image/gif";
  if (data.length >= 12 && data.subarray(0, 4).toString("ascii") === "RIFF" && data.subarray(8, 12).toString("ascii") === "WEBP") return "image/webp";
  if (data.subarray(0, 5).toString("ascii") === "%PDF-") return "application/pdf";

  let text;
  try { text = new TextDecoder("utf-8", { fatal: true }).decode(data).replace(/^\uFEFF/, ""); }
  catch { return "application/octet-stream"; }
  const printable = data.length === 0 || (!data.includes(0) && [...text].filter(char => char === "\n" || char === "\r" || char === "\t" || char >= " ").length / Math.max(1, [...text].length) > 0.92);
  if (!printable) return "application/octet-stream";
  if (/^\s*(?:<\?xml[^>]*>\s*)?<svg(?:\s|>)/i.test(text)) return "image/svg+xml";
  const extension = posix.extname(name).toLowerCase();
  if (extension === ".json") return "application/json";
  if ([".yaml", ".yml"].includes(extension)) return "text/yaml";
  if (extension === ".md") return "text/markdown";
  if (extension === ".csv") return "text/csv";
  return "text/plain";
}

export class SftpFileService {
  constructor(transport) {
    this.transport = transport;
  }

  async session(fn) {
    const sftp = await this.transport.openSftp();
    try { return await fn(sftp); }
    finally { try { sftp.end(); } catch { /* best effort */ } }
  }

  async rootRealpath(sftp, root) {
    const real = await sftpCall(sftp, "realpath", root);
    const attrs = await sftpCall(sftp, "lstat", real);
    ensure(attrs?.isDirectory?.(), "MOUNT_ROOT_INVALID", "Managed volume root is not a directory");
    return String(real).replace(/\/+$/, "");
  }

  async resolveExisting(sftp, root, logicalPath) {
    const normalized = normalizeVolumePath(logicalPath);
    const rootReal = await this.rootRealpath(sftp, root);
    const requested = posix.join(rootReal, ...normalized.segments);
    let attrs;
    try { attrs = await sftpCall(sftp, "lstat", requested); }
    catch (error) {
      if (isNotFound(error)) throw new ExecutorError("FILE_NOT_FOUND", "The requested file path does not exist", { status: 404 });
      throw error;
    }
    ensure(!attrs?.isSymbolicLink?.(), "SYMLINK_NOT_ALLOWED", "Symbolic links are not accessible through the file browser");
    const real = await sftpCall(sftp, "realpath", requested);
    ensure(isWithin(rootReal, real), "PATH_ESCAPE", "Resolved file path escapes the mounted volume");
    return { normalized, rootReal, path: real, attrs };
  }

  async resolveForCreate(sftp, root, logicalPath) {
    const normalized = normalizeVolumePath(logicalPath);
    ensure(normalized.segments.length > 0, "INVALID_PATH", "The volume root cannot be replaced");
    const rootReal = await this.rootRealpath(sftp, root);
    const parentSegments = normalized.segments.slice(0, -1);
    const leaf = normalized.segments.at(-1);
    const parentRequested = posix.join(rootReal, ...parentSegments);
    const parentReal = await sftpCall(sftp, "realpath", parentRequested);
    ensure(isWithin(rootReal, parentReal), "PATH_ESCAPE", "Resolved parent path escapes the mounted volume");
    const parentAttrs = await sftpCall(sftp, "lstat", parentReal);
    ensure(parentAttrs?.isDirectory?.(), "INVALID_PATH", "The destination parent is not a directory");
    const target = posix.join(parentReal, leaf);
    const existing = await lstatOrNull(sftp, target);
    ensure(!existing?.isSymbolicLink?.(), "SYMLINK_NOT_ALLOWED", "A symbolic-link destination cannot be replaced");
    if (existing) {
      const real = await sftpCall(sftp, "realpath", target);
      ensure(isWithin(rootReal, real), "PATH_ESCAPE", "Resolved destination escapes the mounted volume");
    }
    return { normalized, rootReal, parentReal, path: target, attrs: existing };
  }

  async readHead(sftp, path, size) {
    if (!size) return Buffer.alloc(0);
    const handle = await sftpCall(sftp, "open", path, "r");
    const buffer = Buffer.alloc(Math.min(SNIFF_BYTES, size));
    try {
      const [, bytesRead = 0] = await new Promise((resolve, reject) => {
        sftp.read(handle, buffer, 0, buffer.length, 0, (error, count, data) => error ? reject(error) : resolve([data, count]));
      });
      return buffer.subarray(0, bytesRead);
    } finally {
      await sftpCall(sftp, "close", handle).catch(() => {});
    }
  }

  metadata(logical, attrs, mimeType = null) {
    return {
      path: logical,
      name: logical === "/" ? "/" : posix.basename(logical),
      type: fileType(attrs),
      size: Number(attrs?.size || 0),
      mtime: timestamp(attrs?.mtime),
      mode: attrs?.mode ?? null,
      mime_type: mimeType,
    };
  }

  async stat(root, logicalPath) {
    return this.session(async sftp => {
      const resolved = await this.resolveExisting(sftp, root, logicalPath);
      let mime = null;
      if (resolved.attrs?.isFile?.()) mime = sniffMime(resolved.normalized.logical, await this.readHead(sftp, resolved.path, Number(resolved.attrs.size || 0)));
      return this.metadata(resolved.normalized.logical, resolved.attrs, mime);
    });
  }

  async list(root, logicalPath) {
    return this.session(async sftp => {
      const resolved = await this.resolveExisting(sftp, root, logicalPath);
      ensure(resolved.attrs?.isDirectory?.(), "NOT_A_DIRECTORY", "The requested path is not a directory");
      const entries = await sftpCall(sftp, "readdir", resolved.path);
      const items = [];
      for (const entry of entries || []) {
        if (!entry?.filename || entry.filename === "." || entry.filename === "..") continue;
        const childLogical = resolved.normalized.logical === "/" ? `/${entry.filename}` : `${resolved.normalized.logical}/${entry.filename}`;
        const attrs = await lstatOrNull(sftp, posix.join(resolved.path, entry.filename)) || entry.attrs;
        items.push(this.metadata(childLogical, attrs));
      }
      items.sort((left, right) => (left.type === "directory" ? 0 : 1) - (right.type === "directory" ? 0 : 1) || left.name.localeCompare(right.name));
      return { path: resolved.normalized.logical, items };
    });
  }

  async mkdir(root, logicalPath) {
    return this.session(async sftp => {
      const resolved = await this.resolveForCreate(sftp, root, logicalPath);
      ensure(!resolved.attrs, "FILE_EXISTS", "A file or directory already exists at the destination", { status: 409 });
      await sftpCall(sftp, "mkdir", resolved.path, { mode: 0o750 });
      return { ...this.metadata(resolved.normalized.logical, await sftpCall(sftp, "lstat", resolved.path)), created: true };
    });
  }

  async remove(root, logicalPath) {
    return this.session(async sftp => {
      const resolved = await this.resolveExisting(sftp, root, logicalPath);
      ensure(resolved.normalized.logical !== "/", "INVALID_PATH", "The mounted volume root cannot be deleted");
      if (resolved.attrs?.isDirectory?.()) {
        const entries = await sftpCall(sftp, "readdir", resolved.path);
        const children = (entries || []).filter(entry => entry?.filename && entry.filename !== "." && entry.filename !== "..");
        ensure(children.length === 0, "DIRECTORY_NOT_EMPTY", "Only empty directories can be deleted", { status: 409 });
        await sftpCall(sftp, "rmdir", resolved.path);
      }
      else {
        ensure(resolved.attrs?.isFile?.(), "UNSUPPORTED_FILE_TYPE", "Only regular files and empty directories can be deleted");
        await sftpCall(sftp, "unlink", resolved.path);
      }
      return { path: resolved.normalized.logical, deleted: true, type: fileType(resolved.attrs), size: Number(resolved.attrs?.size || 0) };
    });
  }

  async hashResolved(sftp, resolved) {
    ensure(resolved.attrs?.isFile?.(), "NOT_A_FILE", "Checksum is available only for regular files");
    const hash = createHash("sha256");
    await pipeline(
      sftp.createReadStream(resolved.path),
      new Writable({
        write(chunk, _encoding, callback) {
          hash.update(chunk);
          callback();
        },
      }),
    );
    return hash.digest("hex");
  }

  async manifest(root, logicalPaths) {
    ensure(Array.isArray(logicalPaths) && logicalPaths.length >= 1 && logicalPaths.length <= 100, "INVALID_REQUEST", "Validation manifest requires 1 to 100 file paths");
    const unique = [...new Set(logicalPaths)];
    ensure(unique.length === logicalPaths.length, "INVALID_REQUEST", "Validation manifest contains duplicate paths");
    return this.session(async sftp => {
      const files = [];
      for (const logicalPath of unique) {
        let resolved;
        try { resolved = await this.resolveExisting(sftp, root, logicalPath); }
        catch (error) {
          if (error instanceof ExecutorError && error.code === "FILE_NOT_FOUND") {
            files.push({ path: normalizeVolumePath(logicalPath).logical, status: "MISSING", size: null, mime_type: null, sha256: null });
            continue;
          }
          throw error;
        }
        ensure(resolved.attrs?.isFile?.(), "NOT_A_FILE", "Validation manifests can contain only regular files");
        const head = await this.readHead(sftp, resolved.path, Number(resolved.attrs.size || 0));
        files.push({
          ...this.metadata(resolved.normalized.logical, resolved.attrs, sniffMime(resolved.normalized.logical, head)),
          sha256: await this.hashResolved(sftp, resolved), status: "PRESENT",
        });
      }
      return { algorithm: "sha256", files };
    });
  }

  async download(root, logicalPath, writable, onReady) {
    return this.session(async sftp => {
      const resolved = await this.resolveExisting(sftp, root, logicalPath);
      ensure(resolved.attrs?.isFile?.(), "NOT_A_FILE", "Only regular files can be downloaded");
      const head = await this.readHead(sftp, resolved.path, Number(resolved.attrs.size || 0));
      const metadata = this.metadata(resolved.normalized.logical, resolved.attrs, sniffMime(resolved.normalized.logical, head));
      await onReady(metadata);
      await pipeline(sftp.createReadStream(resolved.path), writable);
      return metadata;
    });
  }

  async upload(root, logicalPath, readable, { expectedBytes, maxBytes }) {
    ensure(Number.isInteger(expectedBytes) && expectedBytes >= 0, "INVALID_LENGTH", "Upload length is invalid");
    ensure(expectedBytes <= maxBytes, "FILE_TOO_LARGE", "Upload exceeds the configured file limit", { status: 413 });
    return this.session(async sftp => {
      const resolved = await this.resolveForCreate(sftp, root, logicalPath);
      ensure(!resolved.attrs?.isDirectory?.(), "IS_A_DIRECTORY", "A directory cannot be overwritten by a file", { status: 409 });
      const temporary = posix.join(resolved.parentReal, `.rgw-console-upload-${randomUUID()}`);
      const hash = createHash("sha256");
      let received = 0;
      const meter = new Transform({
        transform(chunk, _encoding, callback) {
          received += chunk.length;
          if (received > expectedBytes || received > maxBytes) return callback(new ExecutorError("FILE_TOO_LARGE", "Upload exceeded its declared or configured size", { status: 413 }));
          hash.update(chunk);
          callback(null, chunk);
        },
      });
      try {
        await pipeline(readable, meter, sftp.createWriteStream(temporary, { flags: "wx", mode: 0o640 }));
        ensure(received === expectedBytes, "INVALID_LENGTH", "Upload length did not match the declared size");
        if (typeof sftp.ext_openssh_rename === "function") await sftpCall(sftp, "ext_openssh_rename", temporary, resolved.path);
        else await sftpCall(sftp, "rename", temporary, resolved.path);
        const attrs = await sftpCall(sftp, "lstat", resolved.path);
        const head = await this.readHead(sftp, resolved.path, Number(attrs.size || 0));
        return { ...this.metadata(resolved.normalized.logical, attrs, sniffMime(resolved.normalized.logical, head)), sha256: hash.digest("hex"), created: !resolved.attrs, overwritten: Boolean(resolved.attrs) };
      } catch (error) {
        await sftpCall(sftp, "unlink", temporary).catch(() => {});
        throw error;
      }
    });
  }
}
