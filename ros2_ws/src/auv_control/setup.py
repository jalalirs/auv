from setuptools import find_packages, setup

package_name = "auv_control"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="AUV Lab",
    maintainer_email="jalalirs@users.noreply.github.com",
    description="Vehicle controllers and thruster allocation.",
    license="Proprietary",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "keyboard_teleop = auv_control.keyboard_teleop:main",
            "reef_keyboard_teleop = auv_control.reef_keyboard_teleop:main",
        ]
    },
)
