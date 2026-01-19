#!/usr/bin/env sh
set -eu

# Install latest ccm release bundle and create convenient symlinks.
#
# Customization via env vars:
# - CCM_GITHUB_REPO: "owner/name" (default: baaaaaaaka/cursor_cli_manager)
# - CCM_INSTALL_TAG: release tag like "v0.5.6" (default: latest)
# - CCM_INSTALL_DEST: install dir (default: ~/.local/bin)
# - CCM_INSTALL_ROOT: extracted bundle root (default: ~/.local/lib/ccm)
# - CCM_INSTALL_FROM_DIR: local dir containing assets + checksums.txt (for offline/test)
# - CCM_INSTALL_OS / CCM_INSTALL_ARCH: override uname detection (for test)
# - CCM_INSTALL_NCURSES_VARIANT: linux ncurses variant override (nc5/nc6/common)

REPO="${CCM_GITHUB_REPO:-baaaaaaaka/cursor_cli_manager}"
TAG="${CCM_INSTALL_TAG:-latest}"
DEST_DIR="${CCM_INSTALL_DEST:-${HOME}/.local/bin}"
ROOT_DIR="${CCM_INSTALL_ROOT:-${HOME}/.local/lib/ccm}"
ASSET_URL_EFFECTIVE=""

OS="${CCM_INSTALL_OS:-$(uname -s)}"
ARCH="${CCM_INSTALL_ARCH:-$(uname -m)}"

case "$(printf '%s' "$ARCH" | tr '[:upper:]' '[:lower:]')" in
  x86_64|amd64) ARCH_NORM="x86_64" ;;
  aarch64|arm64) ARCH_NORM="arm64" ;;
  *) ARCH_NORM="$(printf '%s' "$ARCH" | tr '[:upper:]' '[:lower:]')" ;;
esac

ASSET=""
detect_linux_variant() {
  v="${CCM_INSTALL_NCURSES_VARIANT:-}"
  case "${v}" in
    nc5|nc6|common) printf '%s' "${v}"; return 0 ;;
  esac
  if command -v ldconfig >/dev/null 2>&1; then
    if ldconfig -p 2>/dev/null | grep -q 'libtinfo\.so\.6'; then
      printf '%s' "nc6"
      return 0
    fi
    if ldconfig -p 2>/dev/null | grep -q 'libtinfo\.so\.5'; then
      printf '%s' "nc5"
      return 0
    fi
  fi
  for d in /lib /lib64 /usr/lib /usr/lib64 /usr/local/lib /usr/lib/x86_64-linux-gnu /lib/x86_64-linux-gnu; do
    if [ -e "${d}/libtinfo.so.6" ] || [ -e "${d}/libncursesw.so.6" ]; then
      printf '%s' "nc6"
      return 0
    fi
  done
  for d in /lib /lib64 /usr/lib /usr/lib64 /usr/local/lib /usr/lib/x86_64-linux-gnu /lib/x86_64-linux-gnu; do
    if [ -e "${d}/libtinfo.so.5" ] || [ -e "${d}/libncursesw.so.5" ]; then
      printf '%s' "nc5"
      return 0
    fi
  done
  printf '%s' "common"
  return 0
}

case "${OS}-${ARCH_NORM}" in
  Linux-x86_64)
    VARIANT="$(detect_linux_variant)"
    case "${VARIANT}" in
      nc6) ASSET="ccm-linux-x86_64-nc6.tar.gz" ;;
      nc5) ASSET="ccm-linux-x86_64-nc5.tar.gz" ;;
      *) ASSET="ccm-linux-x86_64-glibc217.tar.gz" ;;
    esac
    ;;
  Darwin-x86_64) ASSET="ccm-macos-x86_64.tar.gz" ;;
  Darwin-arm64) ASSET="ccm-macos-arm64.tar.gz" ;;
  *)
    printf '%s\n' "Unsupported platform: ${OS} ${ARCH}" 1>&2
    exit 2
    ;;
esac

mkdir -p "${DEST_DIR}"
mkdir -p "${ROOT_DIR%/}/versions"

# Cross-process install lock (shared with in-app upgrade).
LOCK_DIR="${ROOT_DIR%/}/.ccm.lock"
LOCK_ACQUIRED="0"
if mkdir "${LOCK_DIR}" 2>/dev/null; then
  LOCK_ACQUIRED="1"
  # Best-effort owner info (helps debugging stale locks).
  {
    printf 'pid=%s\n' "$$"
    printf 'host=%s\n' "$(hostname 2>/dev/null || echo unknown)"
  } > "${LOCK_DIR%/}/owner.txt" 2>/dev/null || true
else
  printf '%s\n' "Another ccm install/upgrade is in progress (lock: ${LOCK_DIR})." 1>&2
  printf '%s\n' "If this is stale, remove it and retry: rm -rf ${LOCK_DIR}" 1>&2
  exit 8
fi

# Create temp files inside DEST_DIR so final mv is atomic.
TMP_BIN="$(mktemp "${DEST_DIR%/}/.ccm.asset.XXXXXX")"
TMP_SUM="$(mktemp "${DEST_DIR%/}/.ccm.sums.XXXXXX")"
TMP_DIR=""
cleanup() {
  rm -f "${TMP_BIN}" "${TMP_SUM}" 2>/dev/null || true
  if [ -n "${TMP_DIR}" ] && [ -d "${TMP_DIR}" ]; then
    rm -rf "${TMP_DIR}" 2>/dev/null || true
  fi
  if [ "${LOCK_ACQUIRED}" = "1" ] && [ -d "${LOCK_DIR}" ]; then
    rm -rf "${LOCK_DIR}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

is_runnable_ccm() {
  # The bundle entrypoint must be a real executable file, not a symlink.
  # (A self-referential symlink would trigger ELOOP at runtime.)
  if [ ! -f "${TARGET}" ]; then
    return 1
  fi
  if [ ! -x "${TARGET}" ]; then
    return 1
  fi
  # -L is widely supported (dash/bash/zsh); treat symlink as broken.
  if [ -L "${TARGET}" ]; then
    return 1
  fi
  return 0
}

install_once() {
  TAG_RESOLVED="$(resolve_tag)"
  VERSIONS_DIR="${ROOT_DIR%/}/versions"
  if [ "${TAG_RESOLVED}" = "latest" ] && [ -z "${CCM_INSTALL_FROM_DIR:-}" ]; then
    # Avoid reusing a potentially broken "versions/latest" directory.
    TAG_RESOLVED="latest-$(date +%s)"
  fi
  FINAL_DIR="${VERSIONS_DIR%/}/${TAG_RESOLVED}"
  CURRENT_LINK="${ROOT_DIR%/}/current"

  # Extract bundle into a temp dir under versions/ (so final rename stays on the same filesystem).
  TMP_DIR="$(mktemp -d "${VERSIONS_DIR%/}/.ccm.extract.XXXXXX")"
  if command -v tar >/dev/null 2>&1; then
    tar -xzf "${TMP_BIN}" -C "${TMP_DIR}"
  else
    printf '%s\n' "Need tar to extract the release bundle." 1>&2
    exit 5
  fi

  if [ ! -f "${TMP_DIR%/}/ccm/ccm" ]; then
    printf '%s\n' "Invalid bundle: missing ccm/ccm in ${ASSET}" 1>&2
    exit 6
  fi
  chmod 755 "${TMP_DIR%/}/ccm/ccm" 2>/dev/null || true

  # Replace version dir (best-effort).
  rm -rf "${FINAL_DIR}" 2>/dev/null || true
  if [ -e "${FINAL_DIR}" ]; then
    # If we couldn't remove it, avoid nesting inside it.
    FINAL_DIR="${FINAL_DIR}.$(date +%s)"
  fi
  mv "${TMP_DIR}" "${FINAL_DIR}"
  TMP_DIR=""

  # Update "current" symlink atomically (best-effort).
  TMP_CUR="${ROOT_DIR%/}/.ccm.current.$$"
  rm -f "${TMP_CUR}" 2>/dev/null || true
  ln -s "${FINAL_DIR}" "${TMP_CUR}"
  # If current is a symlink to a directory, mv would follow it and move inside.
  # Remove existing current to ensure replacement.
  if [ -L "${CURRENT_LINK}" ]; then
    rm -f "${CURRENT_LINK}" 2>/dev/null || true
  elif [ -d "${CURRENT_LINK}" ]; then
    rm -rf "${CURRENT_LINK}" 2>/dev/null || true
  elif [ -e "${CURRENT_LINK}" ]; then
    rm -f "${CURRENT_LINK}" 2>/dev/null || true
  fi
  mv -f "${TMP_CUR}" "${CURRENT_LINK}"

  # Link executable into bin dir.
  TARGET="${CURRENT_LINK%/}/ccm/ccm"
  DEST="${DEST_DIR%/}/ccm"
  if [ -d "${DEST}" ] && [ ! -L "${DEST}" ]; then
    printf '%s\n' "Install failed: ${DEST} is a directory; cannot create ccm symlink there." 1>&2
    exit 9
  fi
  ln -sf "${TARGET}" "${DEST}" 2>/dev/null || true

  # Provide the pip-style alias too (best-effort).
  ALIAS="${DEST_DIR%/}/cursor-cli-manager"
  (
    cd "${DEST_DIR%/}" || exit 0
    ln -sf "ccm" "$(basename "${ALIAS}")" 2>/dev/null || true
  )

  if is_runnable_ccm; then
    printf '%s\n' "Installed ${ASSET} -> ${DEST}"
    printf '%s\n' "Alias: ${ALIAS} -> ${DEST}"
    printf '%s\n' "Bundle: ${CURRENT_LINK} -> ${FINAL_DIR}"
    printf '%s\n' "Tip: ensure ${DEST_DIR} is on your PATH."
    return 0
  fi
  return 1
}

fetch_to() {
  src="$1"
  out="$2"
  if [ -n "${CCM_INSTALL_FROM_DIR:-}" ]; then
    cp "${CCM_INSTALL_FROM_DIR%/}/${src}" "${out}"
    return 0
  fi
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "${src}" -o "${out}"
    return 0
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -qO "${out}" "${src}"
    return 0
  fi
  printf '%s\n' "Need curl or wget to download." 1>&2
  exit 3
}

fetch_text() {
  url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "${url}"
    return 0
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -qO - "${url}"
    return 0
  fi
  return 1
}

resolve_tag() {
  if [ "${TAG}" != "latest" ]; then
    printf '%s' "${TAG}"
    return 0
  fi
  # Offline install can't query the API; keep "latest".
  if [ -n "${CCM_INSTALL_FROM_DIR:-}" ]; then
    printf '%s' "latest"
    return 0
  fi
  api="https://api.github.com/repos/${REPO}/releases/latest"
  txt="$(fetch_text "${api}" 2>/dev/null || true)"
  if [ -z "${txt}" ]; then
    if [ -n "${ASSET_URL_EFFECTIVE:-}" ]; then
      tag="$(printf '%s' "${ASSET_URL_EFFECTIVE}" | sed -n 's#.*/releases/download/\\([^/]*\\)/.*#\\1#p' | head -n 1)"
      if [ -n "${tag}" ]; then
        printf '%s' "${tag}"
        return 0
      fi
    fi
    printf '%s' "latest"
    return 0
  fi
  # Best-effort JSON parsing without jq.
  tag="$(printf '%s' "${txt}" | tr -d '\n' | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\\([^"]*\\)".*/\\1/p' | head -n 1)"
  if [ -n "${tag}" ]; then
    printf '%s' "${tag}"
  else
    if [ -n "${ASSET_URL_EFFECTIVE:-}" ]; then
      tag2="$(printf '%s' "${ASSET_URL_EFFECTIVE}" | sed -n 's#.*/releases/download/\\([^/]*\\)/.*#\\1#p' | head -n 1)"
      if [ -n "${tag2}" ]; then
        printf '%s' "${tag2}"
        return 0
      fi
    fi
    printf '%s' "latest"
  fi
}

if [ -n "${CCM_INSTALL_FROM_DIR:-}" ]; then
  fetch_to "${ASSET}" "${TMP_BIN}"
  if [ -f "${CCM_INSTALL_FROM_DIR%/}/checksums.txt" ]; then
    fetch_to "checksums.txt" "${TMP_SUM}"
  else
    : > "${TMP_SUM}"
  fi
else
  if [ "${TAG}" = "latest" ]; then
    BASE="https://github.com/${REPO}/releases/latest/download"
    if command -v curl >/dev/null 2>&1; then
      # Capture the final URL after redirects so we can infer the real tag without the GitHub API.
      ASSET_URL_EFFECTIVE="$(curl -fsSL -o "${TMP_BIN}" -w "%{url_effective}" "${BASE}/${ASSET}")"
    else
      fetch_to "${BASE}/${ASSET}" "${TMP_BIN}"
    fi
    # checksums are optional
    if fetch_to "${BASE}/checksums.txt" "${TMP_SUM}" 2>/dev/null; then
      :
    else
      : > "${TMP_SUM}"
    fi
  else
    BASE="https://github.com/${REPO}/releases/download/${TAG}"
    fetch_to "${BASE}/${ASSET}" "${TMP_BIN}"
    if fetch_to "${BASE}/checksums.txt" "${TMP_SUM}" 2>/dev/null; then
      :
    else
      : > "${TMP_SUM}"
    fi
  fi
fi

# Verify checksum if we have one.
if [ -s "${TMP_SUM}" ]; then
  EXPECTED="$(awk -v f="${ASSET}" '$NF==f {print $1; exit 0}' "${TMP_SUM}" | tr '[:upper:]' '[:lower:]' || true)"
  if [ -n "${EXPECTED}" ]; then
    ACTUAL=""
    if command -v sha256sum >/dev/null 2>&1; then
      ACTUAL="$(sha256sum "${TMP_BIN}" | awk '{print $1}' | tr '[:upper:]' '[:lower:]')"
    elif command -v shasum >/dev/null 2>&1; then
      ACTUAL="$(shasum -a 256 "${TMP_BIN}" | awk '{print $1}' | tr '[:upper:]' '[:lower:]')"
    fi
    if [ -n "${ACTUAL}" ] && [ "${ACTUAL}" != "${EXPECTED}" ]; then
      printf '%s\n' "Checksum mismatch for ${ASSET}: expected ${EXPECTED}, got ${ACTUAL}" 1>&2
      exit 4
    fi
  fi
fi

if install_once; then
  exit 0
fi

# Auto-repair once on broken installs (common after a symlink-loop upgrade).
printf '%s\n' "Detected a broken ccm install; attempting automatic cleanup and reinstall..." 1>&2
rm -rf "${ROOT_DIR%/}/current" "${ROOT_DIR%/}/versions" 2>/dev/null || true
mkdir -p "${ROOT_DIR%/}/versions"

if install_once; then
  exit 0
fi

printf '%s\n' "Install failed: ${TARGET} is not a runnable executable." 1>&2
printf '%s\n' "Tip: remove ${ROOT_DIR%/} and re-run the installer." 1>&2
exit 7

