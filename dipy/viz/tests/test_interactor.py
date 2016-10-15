import os
import numpy as np
from os.path import join as pjoin
from collections import defaultdict

from dipy.viz import actor, window, interactor
from dipy.viz import utils as vtk_utils
from dipy.data import DATA_DIR
import numpy.testing as npt
from dipy.testing.decorators import xvfb_it

# Conditional import machinery for vtk
from dipy.utils.optpkg import optional_package

# Allow import, but disable doctests if we don't have vtk
vtk, have_vtk, setup_module = optional_package('vtk')

use_xvfb = os.environ.get('TEST_WITH_XVFB', False)
if use_xvfb == 'skip':
    skip_it = True
else:
    skip_it = False


@npt.dec.skipif(not have_vtk or not actor.have_vtk_colors or skip_it)
@xvfb_it
def test_custom_interactor_style_events(recording=False):
    filename = "test_custom_interactor_style_events.log.gz"
    recording_filename = pjoin(DATA_DIR, filename)
    renderer = window.Renderer()

    # the show manager allows to break the rendering process
    # in steps so that the widgets can be added properly
    interactor_style = interactor.CustomInteractorStyle()
    show_manager = window.ShowManager(renderer, size=(800, 800),
                                      interactor_style=interactor_style)

    # Create a cursor, a circle that will follow the mouse.
    polygon_source = vtk.vtkRegularPolygonSource()
    polygon_source.GeneratePolygonOff()  # Only the outline of the circle.
    polygon_source.SetNumberOfSides(50)
    polygon_source.SetRadius(10)
    polygon_source.SetRadius
    polygon_source.SetCenter(0, 0, 0)

    mapper = vtk.vtkPolyDataMapper2D()
    vtk_utils.set_input(mapper, polygon_source.GetOutputPort())

    cursor = vtk.vtkActor2D()
    cursor.SetMapper(mapper)
    cursor.GetProperty().SetColor(1, 0.5, 0)
    renderer.add(cursor)

    def follow_mouse(obj, event):
        event_pos = show_manager.iren.GetEventPosition()
        obj.SetPosition(*event_pos)
        show_manager.render()

    show_manager.iren.GetInteractorStyle().add_active_prop(cursor)
    interactor.add_callback(cursor, "MouseMoveEvent", follow_mouse)

    # create some minimalistic streamlines
    lines = [np.array([[-1, 0, 0.], [1, 0, 0.]]),
             np.array([[-1, 1, 0.], [1, 1, 0.]])]
    colors = np.array([[1., 0., 0.], [0.3, 0.7, 0.]])
    tube1 = actor.streamtube([lines[0]], colors[0])
    tube2 = actor.streamtube([lines[1]], colors[1])
    # renderer.add(stream_actor)
    renderer.add(tube1)
    renderer.add(tube2)

    # Define some counter callback.
    states = defaultdict(lambda: 0)
    def counter(obj, event):
        states[event] += 1

    # Assign the counter callback to every possible event.
    for event in ["CharEvent", "MouseMoveEvent",
                  "KeyPressEvent", "KeyReleaseEvent",
                  "LeftButtonPressEvent", "LeftButtonReleaseEvent",
                  "RightButtonPressEvent", "RightButtonReleaseEvent",
                  "MiddleButtonPressEvent", "MiddleButtonReleaseEvent",
                  "MouseWheelForwardEvent", "MouseWheelBackwardEvent"]:
        interactor.add_callback(tube1, event, counter)

    # Add callback to scale up/down tube1.
    def scale_up_obj(obj, event):
        scale = np.array(obj.GetScale()) + 0.1
        obj.SetScale(*scale)
        show_manager.render()
        return True  # Stop propagating the event.

    def scale_down_obj(obj, event):
        scale = np.array(obj.GetScale()) - 0.1
        obj.SetScale(*scale)
        show_manager.render()
        return True  # Stop propagating the event.

    interactor.add_callback(tube2, "MouseWheelForwardEvent", scale_up_obj)
    interactor.add_callback(tube2, "MouseWheelBackwardEvent", scale_down_obj)

    # Add callback to hide/show tube1.
    def toggle_visibility(obj, event):
        key = show_manager.iren.GetInteractorStyle().GetKeySym()
        if key.lower() == "v":
            obj.SetVisibility(not obj.GetVisibility())
            show_manager.render()

    show_manager.iren.GetInteractorStyle().add_active_prop(tube1)
    show_manager.iren.GetInteractorStyle().add_active_prop(tube2)
    show_manager.iren.GetInteractorStyle().remove_active_prop(tube2)
    interactor.add_callback(tube1, "CharEvent", toggle_visibility)

    if recording:
        show_manager.record_events_to_file(recording_filename)
        print(list(states.items()))
    else:
        show_manager.play_events_from_file(recording_filename)
        msg = ("Wrong count for '{}'.\n"
               "Warning: VTK seems to handle events differently when"
               " LIBGL_ALWAYS_SOFTWARE=1. It is off by default.")

        expected = [('CharEvent', 5),
                    ('KeyPressEvent', 5),
                    ('KeyReleaseEvent', 5),
                    ('MouseMoveEvent', 1398),
                    ('LeftButtonPressEvent', 1),
                    ('RightButtonPressEvent', 1),
                    ('MiddleButtonPressEvent', 1),
                    ('MouseWheelForwardEvent', 1),
                    ('LeftButtonReleaseEvent', 1),
                    ('RightButtonReleaseEvent', 1),
                    ('MouseWheelBackwardEvent', 2),
                    ('MiddleButtonReleaseEvent', 1)]

        # Useful loop for debugging.
        for event, count in expected:
            if states[event] != count:
                print("{}: {} vs. {} (expected)".format(event, states[event], count))

        for event, count in expected:
            npt.assert_equal(states[event], count, err_msg=msg.format(event))


if __name__ == '__main__':
    test_custom_interactor_style_events(recording=True)