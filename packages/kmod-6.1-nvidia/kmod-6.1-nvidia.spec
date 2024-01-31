%global tesla_major 470
%global tesla_minor 223
%global tesla_patch 02
%global tesla_ver %{tesla_major}.%{tesla_minor}.%{tesla_patch}
%global spdx_id %(bottlerocket-license-tool -l %{_builddir}/Licenses.toml spdx-id nvidia)
%global license_file %(bottlerocket-license-tool -l %{_builddir}/Licenses.toml path nvidia -p ./licenses)

# With the split of the firmware binary from firmware/gsp.bin to firmware/gsp_ga10x.bin
# and firmware/gsp_tu10x.bin the file format changed from executable to relocatable.
# The __spec_install_post macro will by default try to strip all binary files.
# Unfortunately the strip used is not compatible with the new file format.
# Redefine strip, so that these firmware binaries do not derail the build.
%global __strip /usr/bin/true

Name: %{_cross_os}kmod-6.1-nvidia
Version: 1.0.0
Release: 1%{?dist}
Summary: NVIDIA drivers for the 6.1 kernel
# We use these licences because we only ship our own software in the main package,
# each subpackage includes the LICENSE file provided by the Licenses.toml file
License: Apache-2.0 OR MIT
URL: http://www.nvidia.com/

# NVIDIA .run scripts from 0 to 199
Source0: https://us.download.nvidia.com/tesla/%{tesla_ver}/NVIDIA-Linux-x86_64-%{tesla_ver}.run
Source1: https://us.download.nvidia.com/tesla/%{tesla_ver}/NVIDIA-Linux-aarch64-%{tesla_ver}.run

# Common NVIDIA conf files from 200 to 299
Source200: nvidia-tmpfiles.conf.in
Source202: nvidia-dependencies-modules-load.conf

# NVIDIA tesla conf files from 300 to 399
Source300: nvidia-tesla-tmpfiles.conf.in
Source301: nvidia-tesla-build-config.toml.in
Source302: nvidia-tesla-path.env.in
Source303: nvidia-ld.so.conf.in

BuildRequires: %{_cross_os}glibc-devel
BuildRequires: %{_cross_os}kernel-6.1-archive

%description
%{summary}.

%package tesla-%{tesla_major}
Summary: NVIDIA %{tesla_major} Tesla driver
Version: %{tesla_ver}
License: %{spdx_id}
Requires: %{name}

%description tesla-%{tesla_major}
%{summary}

%prep
# Extract nvidia sources with `-x`, otherwise the script will try to install
# the driver in the current run
sh %{_sourcedir}/NVIDIA-Linux-%{_cross_arch}-%{tesla_ver}.run -x

%global kernel_sources %{_builddir}/kernel-devel
tar -xf %{_cross_datadir}/bottlerocket/kernel-devel.tar.xz

%build
pushd NVIDIA-Linux-%{_cross_arch}-%{tesla_ver}/kernel

# This recipe was based in the NVIDIA yum/dnf specs:
# https://github.com/NVIDIA/yum-packaging-precompiled-kmod

# We set IGNORE_CC_MISMATCH even though we are using the same compiler used to compile the kernel, if
# we don't set this flag the compilation fails
make %{?_smp_mflags} ARCH=%{_cross_karch} IGNORE_CC_MISMATCH=1 SYSSRC=%{kernel_sources} CC=%{_cross_target}-gcc LD=%{_cross_target}-ld

%{_cross_target}-strip -g --strip-unneeded nvidia/nv-interface.o
%{_cross_target}-strip -g --strip-unneeded nvidia-uvm.o
%{_cross_target}-strip -g --strip-unneeded nvidia-drm.o
%{_cross_target}-strip -g --strip-unneeded nvidia-peermem/nvidia-peermem.o
%{_cross_target}-strip -g --strip-unneeded nvidia-modeset/nv-modeset-interface.o

# We delete these files since we just stripped the input .o files above, and
# will be build at runtime in the host
rm nvidia{,-modeset,-peermem}.o

# Delete the .ko files created in make command, just to be safe that we
# don't include any linked module in the base image
rm nvidia{,-modeset,-peermem,-drm}.ko

popd

%install
install -d %{buildroot}%{_cross_libexecdir}
install -d %{buildroot}%{_cross_libdir}
install -d %{buildroot}%{_cross_tmpfilesdir}
install -d %{buildroot}%{_cross_unitdir}
install -d %{buildroot}%{_cross_factorydir}%{_cross_sysconfdir}/{drivers,ld.so.conf.d}

KERNEL_VERSION=$(cat %{kernel_sources}/include/config/kernel.release)
sed \
  -e "s|__KERNEL_VERSION__|${KERNEL_VERSION}|" \
  -e "s|__PREFIX__|%{_cross_prefix}|" %{S:200} > nvidia.conf
install -p -m 0644 nvidia.conf %{buildroot}%{_cross_tmpfilesdir}

# Install modules-load.d drop-in to autoload required kernel modules
install -d %{buildroot}%{_cross_libdir}/modules-load.d
install -p -m 0644 %{S:202} %{buildroot}%{_cross_libdir}/modules-load.d/nvidia-dependencies.conf

# Begin NVIDIA tesla driver
pushd NVIDIA-Linux-%{_cross_arch}-%{tesla_ver}
# We install bins and libs in a versioned directory to prevent collisions with future drivers versions
install -d %{buildroot}%{_cross_libexecdir}/nvidia/tesla/bin/%{tesla_ver}
install -d %{buildroot}%{_cross_libdir}/nvidia/tesla/%{tesla_ver}
install -d %{buildroot}%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d
install -d %{buildroot}%{_cross_factorydir}/nvidia/tesla/%{tesla_ver}

sed -e 's|__NVIDIA_VERSION__|%{tesla_ver}|' %{S:300} > nvidia-tesla-%{tesla_ver}.conf
install -m 0644 nvidia-tesla-%{tesla_ver}.conf %{buildroot}%{_cross_tmpfilesdir}/
sed -e 's|__NVIDIA_MODULES__|%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d/|' %{S:301} > \
  nvidia-tesla-%{tesla_ver}.toml
install -m 0644 nvidia-tesla-%{tesla_ver}.toml %{buildroot}%{_cross_factorydir}%{_cross_sysconfdir}/drivers
# Install nvidia-path environment file, will be used as a drop-in for containerd.service since
# libnvidia-container locates and mounts helper binaries into the containers from either
# `PATH` or `NVIDIA_PATH`
sed -e 's|__NVIDIA_BINDIR__|%{_cross_libexecdir}/nvidia/tesla/bin/%{tesla_ver}|' %{S:302} > nvidia-path.env
install -m 0644 nvidia-path.env %{buildroot}%{_cross_factorydir}/nvidia/tesla/%{tesla_ver}
# We need to add `_cross_libdir/tesla_470` to the paths loaded by the ldconfig service
# because libnvidia-container uses the `ldcache` file created by the service, to locate and mount the
# libraries into the containers
sed -e 's|__LIBDIR__|%{_cross_libdir}|' %{S:303} | sed -e 's|__NVIDIA_VERSION__|%{tesla_ver}|' \
  > nvidia-tesla-%{tesla_ver}.conf
install -m 0644 nvidia-tesla-%{tesla_ver}.conf %{buildroot}%{_cross_factorydir}%{_cross_sysconfdir}/ld.so.conf.d/

# driver
install kernel/nvidia.mod.o %{buildroot}%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d
install kernel/nvidia/nv-interface.o %{buildroot}%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d
install kernel/nvidia/nv-kernel.o_binary %{buildroot}%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d/nv-kernel.o

# uvm
install kernel/nvidia-uvm.mod.o %{buildroot}%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d
install kernel/nvidia-uvm.o %{buildroot}%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d

# modeset
install kernel/nvidia-modeset.mod.o %{buildroot}%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d
install kernel/nvidia-modeset/nv-modeset-interface.o %{buildroot}%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d
install kernel/nvidia-modeset/nv-modeset-kernel.o %{buildroot}%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d

# peermem
install kernel/nvidia-peermem.mod.o %{buildroot}%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d
install kernel/nvidia-peermem/nvidia-peermem.o %{buildroot}%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d

# drm
install kernel/nvidia-drm.mod.o %{buildroot}/%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d
install kernel/nvidia-drm.o %{buildroot}/%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d

# Binaries
install -m 755 nvidia-smi %{buildroot}%{_cross_libexecdir}/nvidia/tesla/bin/%{tesla_ver}
install -m 755 nvidia-debugdump %{buildroot}%{_cross_libexecdir}/nvidia/tesla/bin/%{tesla_ver}
install -m 755 nvidia-cuda-mps-control %{buildroot}%{_cross_libexecdir}/nvidia/tesla/bin/%{tesla_ver}
install -m 755 nvidia-cuda-mps-server %{buildroot}%{_cross_libexecdir}/nvidia/tesla/bin/%{tesla_ver}
%if "%{_cross_arch}" == "x86_64"
install -m 755 nvidia-ngx-updater %{buildroot}%{_cross_libexecdir}/nvidia/tesla/bin/%{tesla_ver}
%endif

# We install all the libraries, and filter them out in the 'files' section, so we can catch
# when new libraries are added
install -m 755 *.so* %{buildroot}/%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/

# This library has the same SONAME as libEGL.so.1.1.0, this will cause collisions while
# the symlinks are created. For now, we only symlink libEGL.so.1.1.0.
EXCLUDED_LIBS="libEGL.so.%{tesla_ver}"

for lib in $(find . -maxdepth 1 -type f -name 'lib*.so.*' -printf '%%P\n'); do
  [[ "${EXCLUDED_LIBS}" =~ "${lib}" ]] && continue
  soname="$(%{_cross_target}-readelf -d "${lib}" | awk '/SONAME/{print $5}' | tr -d '[]')"
  [ -n "${soname}" ] || continue
  [ "${lib}" == "${soname}" ] && continue
  ln -s "${lib}" %{buildroot}/%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/"${soname}"
done

popd

%files
%{_cross_attribution_file}
%dir %{_cross_libexecdir}/nvidia
%dir %{_cross_libdir}/nvidia
%dir %{_cross_datadir}/nvidia
%dir %{_cross_libdir}/modules-load.d
%dir %{_cross_factorydir}%{_cross_sysconfdir}/drivers
%{_cross_tmpfilesdir}/nvidia.conf
%{_cross_libdir}/systemd/system/
%{_cross_libdir}/modules-load.d/nvidia-dependencies.conf

%files tesla-%{tesla_major}
%license %{license_file}
%dir %{_cross_datadir}/nvidia/tesla/%{tesla_ver}
%dir %{_cross_libexecdir}/nvidia/tesla/bin/%{tesla_ver}
%dir %{_cross_libdir}/nvidia/tesla/%{tesla_ver}
%dir %{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d
%dir %{_cross_factorydir}/nvidia/tesla/%{tesla_ver}

# Binaries
%{_cross_libexecdir}/nvidia/tesla/bin/%{tesla_ver}/nvidia-debugdump
%{_cross_libexecdir}/nvidia/tesla/bin/%{tesla_ver}/nvidia-smi

# Configuration files
%{_cross_factorydir}%{_cross_sysconfdir}/drivers/nvidia-tesla-%{tesla_ver}.toml
%{_cross_factorydir}%{_cross_sysconfdir}/ld.so.conf.d/nvidia-tesla-%{tesla_ver}.conf
%{_cross_factorydir}/nvidia/tesla/%{tesla_ver}/nvidia-path.env

# driver
%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d/nvidia.mod.o
%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d/nv-interface.o
%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d/nv-kernel.o

# uvm
%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d/nvidia-uvm.mod.o
%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d/nvidia-uvm.o

# modeset
%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d/nv-modeset-interface.o
%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d/nv-modeset-kernel.o
%{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d/nvidia-modeset.mod.o

# tmpfiles
%{_cross_tmpfilesdir}/nvidia-tesla-%{tesla_ver}.conf

# We only install the libraries required by all the DRIVER_CAPABILITIES, described here:
# https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/user-guide.html#driver-capabilities

# Utility libs
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-ml.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-ml.so.1
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-cfg.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-cfg.so.1
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-nvvm.so.4.0.0
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-nvvm.so.4

# Compute libs
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libcuda.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libcuda.so.1
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-opencl.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-opencl.so.1
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-ptxjitcompiler.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-ptxjitcompiler.so.1
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-allocator.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-allocator.so.1
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libOpenCL.so.1.0.0
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libOpenCL.so.1
%if "%{_cross_arch}" == "x86_64"
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-compiler.so.%{tesla_ver}
%endif

# Video libs
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libvdpau_nvidia.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libvdpau_nvidia.so.1
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-encode.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-encode.so.1
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-opticalflow.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-opticalflow.so.1
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvcuvid.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvcuvid.so.1

# Graphics libs
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-eglcore.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-glcore.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-tls.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-glsi.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-rtcore.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-fbc.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-fbc.so.1
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvoptix.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvoptix.so.1
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-vulkan-producer.so.%{tesla_ver}
%if "%{_cross_arch}" == "x86_64"
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-ifr.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-ifr.so.1
%endif

# Graphics GLVND libs
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-glvkspirv.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-cbl.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libGLX_nvidia.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libGLX_nvidia.so.0
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libEGL_nvidia.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libEGL_nvidia.so.0
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libGLESv2_nvidia.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libGLESv2_nvidia.so.2
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libGLESv1_CM_nvidia.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libGLESv1_CM_nvidia.so.1

# Graphics compat
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libEGL.so.1.1.0
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libEGL.so.1
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libEGL.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libGL.so.1.7.0
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libGL.so.1
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libGLESv1_CM.so.1.2.0
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libGLESv1_CM.so.1
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libGLESv2.so.2.1.0
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libGLESv2.so.2

# NGX
%if "%{_cross_arch}" == "x86_64"
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-ngx.so.%{tesla_ver}
%{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-ngx.so.1
%endif

# Neither nvidia-peermem nor nvidia-drm are included in driver container images, we exclude them
# for now, and we will add them if requested
%exclude %{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d/nvidia-peermem.mod.o
%exclude %{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d/nvidia-peermem.o
%exclude %{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d/nvidia-drm.mod.o
%exclude %{_cross_datadir}/nvidia/tesla/%{tesla_ver}/module-objects.d/nvidia-drm.o
%exclude %{_cross_libexecdir}/nvidia/tesla/bin/%{tesla_ver}/nvidia-cuda-mps-control
%exclude %{_cross_libexecdir}/nvidia/tesla/bin/%{tesla_ver}/nvidia-cuda-mps-server
%if "%{_cross_arch}" == "x86_64"
%exclude %{_cross_libexecdir}/nvidia/tesla/bin/%{tesla_ver}/nvidia-ngx-updater
%endif

# None of these libraries are required by libnvidia-container, so they
# won't be used by a containerized workload
%exclude %{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libGLX.so.0
%exclude %{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libGLdispatch.so.0
%exclude %{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libOpenGL.so.0
%exclude %{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libglxserver_nvidia.so.%{tesla_ver}
%exclude %{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-egl-wayland.so.1.1.7
%exclude %{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-gtk2.so.%{tesla_ver}
%exclude %{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-gtk3.so.%{tesla_ver}
%exclude %{_cross_libdir}/nvidia/tesla/%{tesla_ver}/nvidia_drv.so
%exclude %{_cross_libdir}/nvidia/tesla/%{tesla_ver}/libnvidia-egl-wayland.so.1
