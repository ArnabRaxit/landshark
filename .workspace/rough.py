
from osgeo import gdal
import os
import numpy as np

alltifs = [os.path.join('/landshark/compare_con_images', x) for x in os.listdir("/landshark/compare_con_images")]
datasets = {x:gdal.Open(x, gdal.GA_ReadOnly) for x in alltifs }
ldatasets = [(x,gdal.Open(x, gdal.GA_ReadOnly)) for x in alltifs ]

tif_info = [ (x[0],x[1].GetProjection(),x[1].GetGeoTransform())  for x in ldatasets]

#print(datasets)
#print(tif_info)

np_tif_info = np.asarray(tif_info)

print(np_tif_info)