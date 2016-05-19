import vtk

from dipy.data import *

def computeBounds( renderer, normalized_display_position, size ):
    upperRight = vtk.vtkCoordinate()
    upperRight.SetCoordinateSystemToNormalizedDisplay()
    upperRight.SetValue( normalized_display_position[0], normalized_display_position[1] )
    print(upperRight.GetComputedDisplayValue(renderer))
    bds = [0.0]*6
    bds[0] = upperRight.GetComputedDisplayValue(renderer)[0] - size[0]
    bds[1] = bds[0] + size[0]
    bds[2] = upperRight.GetComputedDisplayValue(renderer)[1] - size[1]
    bds[3] = bds[2] + size[1]
    return bds

def button_callback(obj, event):
    print('button pressed')

fetch_viz_icons()
filename = read_viz_icons(fname='stop2.png')

ren = vtk.vtkRenderer()
renWin = vtk.vtkRenderWindow()
renWin.AddRenderer(ren)
iren = vtk.vtkRenderWindowInteractor()
iren.SetRenderWindow(renWin)
iren.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())

reader = vtk.vtkPNGReader()
reader.SetFileName(filename)
reader.Update()

buttonRepresentation = vtk.vtkTexturedButtonRepresentation2D()
buttonRepresentation.SetNumberOfStates(1)
buttonRepresentation.SetButtonTexture(0, reader.GetOutput())

position = [0, 0] 
size = [100, 100] 
bounds = computeBounds(ren, position, size)

print("Bounds = ", bounds)

buttonWidget = vtk.vtkButtonWidget()
buttonWidget.SetInteractor(iren)
buttonRepresentation.PlaceWidget(bounds)
buttonWidget.SetRepresentation(buttonRepresentation)
buttonWidget.AddObserver(vtk.vtkCommand.StateChangedEvent, button_callback)

iren.Initialize()
buttonWidget.On()
renWin.Render()
iren.Start()