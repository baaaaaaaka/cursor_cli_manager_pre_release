FROM quay.io/pypa/manylinux2014_x86_64:latest

# Build-time versions (pinned for reproducibility).
ARG OPENSSL_VER=3.0.13
ARG PYVER=3.11.14

# Build deps needed for Python modules we rely on:
# - libffi-devel: _ctypes
# - ncurses-devel: _curses (TUI)
# - sqlite-devel: sqlite3 (chat DB)
RUN yum -y install perl-IPC-Cmd libffi-devel ncurses-devel sqlite-devel >/dev/null && yum clean all

# Build OpenSSL into /opt/openssl (so we can build Python with working _ssl/_hashlib).
RUN set -euxo pipefail; \
    cd /tmp; \
    curl -fsSLO "https://www.openssl.org/source/openssl-${OPENSSL_VER}.tar.gz"; \
    tar -xf "openssl-${OPENSSL_VER}.tar.gz"; \
    cd "openssl-${OPENSSL_VER}"; \
    ./Configure linux-x86_64 --prefix=/opt/openssl --openssldir=/opt/openssl --libdir=lib shared zlib; \
    make -j"$(nproc)"; \
    make install_sw; \
    rm -rf "/tmp/openssl-${OPENSSL_VER}" "/tmp/openssl-${OPENSSL_VER}.tar.gz"

# Build shared CPython into /opt/python so PyInstaller works.
RUN set -euxo pipefail; \
    cd /tmp; \
    curl -fsSLO "https://www.python.org/ftp/python/${PYVER}/Python-${PYVER}.tgz"; \
    tar -xf "Python-${PYVER}.tgz"; \
    cd "Python-${PYVER}"; \
    export CPPFLAGS="-I/opt/openssl/include"; \
    export LDFLAGS="-L/opt/openssl/lib"; \
    export LD_LIBRARY_PATH="/opt/openssl/lib"; \
    ./configure --prefix=/opt/python --enable-shared --with-openssl=/opt/openssl --with-openssl-rpath=no --with-ensurepip=install; \
    make -j"$(nproc)"; \
    make install; \
    rm -rf "/tmp/Python-${PYVER}" "/tmp/Python-${PYVER}.tgz"

ENV PATH="/opt/python/bin:${PATH}"
ENV LD_LIBRARY_PATH="/opt/python/lib:/opt/openssl/lib"
ENV PIP_DISABLE_PIP_VERSION_CHECK="1"

# Install build tooling once (release jobs won't hit PyPI).
RUN set -euxo pipefail; \
    python3 -m pip install -U pip "setuptools<69" wheel pyinstaller

