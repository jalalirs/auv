# GPU host readiness

- Audit date: 2026-08-27
- Scope: read-only inspection through Tailscale
- Execution status: **isolated Isaac 6.0.1 container approved on GPU 1; host
  upgrade remains on hold**

## Outcome

The workstation has excellent CPU, RAM, and GPU capacity. Its host operating
system is outside the documented Isaac 6.0.1 workstation requirements, and it
remains a shared, production-like machine with no verified out-of-band recovery
path. Therefore an in-place operating-system or NVIDIA driver upgrade is
rejected.

After GPU 1 and storage were reclaimed, however, the official Isaac 6.0.1
container compatibility checker passed with the current 580.126.09 driver. M0
can proceed in an isolated Ubuntu 24.04 container on GPU 1 without changing the
host boot path. A clean Ubuntu 24.04 host remains the long-term production
target rather than an immediate blocker.

## Observed inventory

| Area | Observation | Assessment |
| --- | --- | --- |
| Host | Ubuntu 20.04.6, kernel 5.15.0-139, x86_64 bare metal | Unsupported by current Isaac Sim |
| CPU | AMD Ryzen Threadripper 7960X, 24 cores / 48 threads | Excellent |
| Memory | 125 GiB RAM; 2 GiB swap with about 1.7 GiB used | RAM excellent; swap too small for a shared build host |
| GPU 0 | RTX 5880 Ada, 48 GiB; about 42.2 GiB free | Strong candidate, but already shared by six processes |
| GPU 1 | RTX 5880 Ada, 48 GiB; about 3.6 GiB free | Unavailable for Isaac while the current model workload runs |
| Driver | NVIDIA 580.126.09 | Suitable generation for the 5.1 lab; below the 595.58.03 version tested with 6.0 |
| Storage | 2 TB Kingston NVMe; root at 91%, about 167 GiB free | Not enough operational headroom for the twin and caches |
| Docker | 53 images, 87 containers, 31 volumes; 79 containers active | Shared production-like runtime |
| Docker usage | 110 GB images and 234 GB volumes | Almost all active; only about 11 GB reported reclaimable |
| K3s | Active single-node control plane with MinIO and PostgreSQL PVCs | Upgrade/reboot has stateful-service impact |
| Boot | Secure Boot enabled; EFI partition healthy | Driver changes may require console-time MOK enrollment |
| Recovery | Tailscale and SSH active; `ipmitool` absent | Out-of-band console and power recovery are unverified |

The home directory is about 1.3 TB. Its largest visible areas include roughly
704 GB under `code`, 151 GB under `Documents`, 126 GB under `.cache`, 76 GB
under `stt-train`, and 35 GB under `models`. These figures identify candidates
for a separate ownership review; they do **not** authorize deletion.

## Post-audit change log

On 2026-08-27, the retired `zameel-qwen35-35b-a3b` vLLM container was stopped
after confirming that port 8011 had no active connections. Its automatic
restart policy was disabled. GPU 1 changed from about 3.6 GiB free to 44.6 GiB
free. The independent embedding service remains active and uses about 3.9 GiB.

After explicit deletion approval, the stopped container, its exclusively used
20 GB vLLM image, and `/home/jalalirs/models/qwen35` were permanently removed.
Absence checks passed and 55 GiB was recovered, taking the root filesystem from
91% to 88% used with about 221 GiB available before the Isaac image pull.
Docker, K3s, SSH, Tailscale, and the other 78 running containers remained
active after the change.

The motherboard identifies as an ASUS Pro WS TRX50-SAGE WIFI. No BMC device,
IPMI interface, or installed remote-console utility was detected. Therefore an
in-place remote OS upgrade remains disallowed until a physical recovery path
exists, even if downtime for the hosted services is accepted.

The official Isaac Sim 6.0.1 image was then pulled and its compatibility
checker was run with only GPU 1 exposed. The checker returned `PASSED`, accepted
driver 580.126.09, identified the RTX 5880 Ada and its VRAM as excellent, and
accepted the container's Ubuntu 24.04.3 userspace. See the
[compatibility audit](audits/2026-08-27-isaac-6.0.1-compatibility.md).

## Compatibility gaps

The [Isaac Sim 6.0 requirements](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html)
specify Ubuntu 22.04 or 24.04 and list Linux driver 595.58.03 as the tested
version. The current Ubuntu 20.04 host and 580 driver therefore fail the
supported-platform gate even though its CPU, RAM, GPU, and VRAM are strong.

NVIDIA lists 50 GB SSD as the minimum, 500 GB SSD as the good tier, and 1 TB
NVMe as ideal. Those values are hardware tiers, not safe-free-space targets.
For this project, reserve at least 500 GB on a dedicated filesystem and keep at
least 20% free so application packages, shader caches, container layers, reef
assets, synthetic data, and rollback copies cannot fill the shared root disk.

## Risk register

| Risk | Why it matters | Required control |
| --- | --- | --- |
| Shared-service outage | Docker, K3s, databases, model serving, and other projects use the host | Migrate or quiesce workloads under an approved maintenance window |
| Failed remote boot | OS, kernel, and driver work can remove SSH or GPU access | Verified physical or out-of-band console before any rebooting change |
| Secure Boot enrollment | New third-party kernel modules can require MOK interaction on reboot | Local-console owner and tested enrollment procedure |
| Irreversible state loss | Stateful Docker/K3s volumes occupy hundreds of GB | Versioned backup plus an actual restore test |
| Disk exhaustion | Root is already at 91% | Dedicated project storage and free-space alarms |
| GPU contention | Both GPUs currently serve other processes | Explicit GPU 0 reservation and workload-owner agreement |
| Extension lock-in | Underwater projects trail Isaac releases | Stable project-owned USD/data contracts and adapter isolation |

Canonical documents state that release upgrades should be performed
sequentially between LTS versions, that third-party repositories are disabled,
and that backups are essential. Ubuntu also documents that Secure Boot may
require Machine Owner Key enrollment for third-party modules:

- [Ubuntu Server release-upgrade guidance](https://documentation.ubuntu.com/server/how-to/software/upgrade-your-release/)
- [Ubuntu Secure Boot and MOK behavior](https://documentation.ubuntu.com/security/docs/security-features/platform-protections/secure-boot/)

## Approved architecture; pending execution approval

### Preferred route

1. Provision a dedicated Ubuntu 24.04 environment for Isaac. Prefer a separate
   workstation. If the same chassis must be reused, first migrate its active
   services elsewhere and install onto a new system NVMe while retaining the
   original disk untouched as the rollback image.
2. Provide at least 1 TB dedicated NVMe storage for runtime, caches, assets, and
   experiments. Keep bulk source data outside Git.
3. Verify local or out-of-band console access, boot selection, backups, and one
   stateful restore before changing the operating system or driver.
4. Install the NVIDIA driver version pinned in `runtime.yaml`, validate both
   GPUs, then install Docker and NVIDIA Container Toolkit.
5. Reserve GPU 0 for the simulator during scheduled sessions. Do not assume GPU
   1 is available while the current inference workload is running.
6. Run NVIDIA's Isaac compatibility checker before downloading the full
   runtime.
7. Launch the minimal project USD scene and WebRTC stream before adding reef
   assets, ROS, OceanSim, or custom extensions.

### Temporary compatibility lab

If a dedicated target is delayed, Isaac Sim 5.1 may be tested in an isolated,
disposable container on GPU 0 after storage and scheduling approval. This does
not make the current host supported: NVIDIA no longer supports Isaac 5.1 and
does not list Ubuntu 20.04 for it. The lab exists only to inspect OceanSim and
IsaacSim Underwater behavior and estimate porting work.

Do not pull the Isaac image on the current 91%-full disk, change its NVIDIA
driver, stop workloads, or prune active data as part of that evaluation.

## Rollback gates

The canonical installation may begin only when all of these are true:

- [ ] Target Ubuntu 24.04 environment is isolated from active production data.
- [ ] At least 500 GB is reserved for the project on a dedicated filesystem.
- [ ] Backups exist and a representative stateful restore has succeeded.
- [ ] Physical or out-of-band console and reboot recovery have been tested.
- [ ] Secure Boot and NVIDIA module-enrollment procedure has an owner.
- [ ] GPU 0 usage window and service impact have been agreed.
- [ ] Current disk or machine can be restored without reconstructing it live.
