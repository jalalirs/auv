from setuptools import find_packages, setup

package_name = "auv_perception"

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
    description="Sensor preprocessing and perception nodes.",
    license="Proprietary",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "sonar_point_cloud_filter = "
            "auv_perception.sonar_point_cloud_filter:main",
        ]
    },
)
