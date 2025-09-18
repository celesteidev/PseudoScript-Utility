#!/bin/bash
set -e

# Configuration
PACKAGE_NAME="psu"
VERSION="0.1.0"
ARCH="all"
BUILD_DIR="../build"
PACKAGE_DIR="${BUILD_DIR}/${PACKAGE_NAME}_${VERSION}_${ARCH}"

echo "Building PseudoScript Utility Debian package..."

# Clean previous builds
rm -rf ${BUILD_DIR}
mkdir -p ${PACKAGE_DIR}

# Copy the debian package structure
cp -r debian/* ${PACKAGE_DIR}/

# COPY THE INTERPRETER CODE - FIXED PATH!
# From packages directory, the interpreter is at ../interpreter/
echo "Copying interpreter files..."
cp -r ../interpreter/* ${PACKAGE_DIR}/usr/lib/psu/interpreter/

# Set permissions
chmod -R 755 ${PACKAGE_DIR}/DEBIAN
chmod 644 ${PACKAGE_DIR}/usr/share/doc/psu/*
chmod 644 ${PACKAGE_DIR}/usr/share/man/man1/*

# Build the package
echo "Building Debian package..."
dpkg-deb --build ${PACKAGE_DIR}

# Move the package to packages directory
mv ${BUILD_DIR}/${PACKAGE_NAME}_${VERSION}_${ARCH}.deb ./

echo "Package built successfully: ${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
echo ""
echo "To install: sudo dpkg -i ${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
echo "To remove:   sudo dpkg -r psu"
