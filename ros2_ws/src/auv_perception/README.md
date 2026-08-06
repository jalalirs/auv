# AUV perception

Sensor preprocessing and perception nodes live here. The First Dive launch uses
`sonar_point_cloud_filter` to remove non-finite returns from DAVE's full
organized sonar cloud and publish a decimated `/auv/sonar/point_cloud` stream
for interactive Foxglove visualization. The raw cloud remains unchanged for
recording and future perception work.
