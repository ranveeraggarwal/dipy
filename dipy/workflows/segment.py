from __future__ import division, print_function, absolute_import

from glob import glob
from os.path import join, basename, splitext

import nibabel as nib
import numpy as np
from time import time
from dipy.workflows.utils import (choose_create_out_dir,
                                  bool_param)
from dipy.segment.mask import median_otsu
from dipy.workflows.align import load_trk, save_trk
import os
import numpy as np
from dipy.utils.six import string_types
from glob import glob
from dipy.segment.bundles import RecoBundles, KDTreeBundles
from dipy.tracking.streamline import transform_streamlines
from nibabel import trackvis as tv
from dipy.io.pickles import save_pickle, load_pickle


def median_otsu_flow(input_files, out_dir='', save_masked=False,
                     median_radius=4, numpass=4, autocrop=False,
                     vol_idx=None, dilate=None):
    """ Workflow wrapping the median_otsu segmentation method.

    It applies median_otsu segmentation on each file found by 'globing'
    ``input_files`` and saves the results in a directory specified by
    ``out_dir``.

    Parameters
    ----------
    input_files : string
        Path to the input volumes. This path may contain wildcards to process
        multiple inputs at once.
    out_dir : string, optional
        Output directory (default input file directory)
    save_masked : bool
        Save mask
    median_radius : int, optional
        Radius (in voxels) of the applied median filter(default 4)
    numpass : int, optional
        Number of pass of the median filter (default 4)
    autocrop : bool, optional
        If True, the masked input_volumes will also be cropped using the
        bounding box defined by the masked data. Should be on if DWI is
        upsampled to 1x1x1 resolution. (default False)
    vol_idx : string, optional
        1D array representing indices of ``axis=3`` of a 4D `input_volume`
        'None' (the default) corresponds to ``(0,)`` (assumes first volume in
        4D array)
    dilate : string, optional
        number of iterations for binary dilation (default 'None')
    """
    for fpath in glob(input_files):
        print('')
        print('Applying median_otsu segmentation on {0}'.format(fpath))
        img = nib.load(fpath)
        volume = img.get_data()

        masked, mask = median_otsu(volume, median_radius,
                                   numpass, autocrop,
                                   vol_idx, dilate)

        fname, ext = splitext(basename(fpath))
        if(fname.endswith('.nii')):
            fname, _ = splitext(fname)
            ext = '.nii.gz'

        mask_fname = fname + '_mask' + ext

        out_dir_path = choose_create_out_dir(out_dir, fpath)

        mask_img = nib.Nifti1Image(mask.astype(np.float32), img.get_affine())
        mask_out_path = join(out_dir_path, mask_fname)
        mask_img.to_filename(mask_out_path)
        print('Mask saved as {0}'.format(mask_out_path))

        if bool_param(save_masked):
            masked_fname = fname + '_bet' + ext
            masked_img = nib.Nifti1Image(masked,
                                         img.get_affine(), img.get_header())
            masked_out_path = join(out_dir_path, masked_fname)
            masked_img.to_filename(masked_out_path)
            print('Masked volume saved as {0}'.format(masked_out_path))


def show_bundles(static, moving, linewidth=1., tubes=False,
                 opacity=1., fname=None):

    from dipy.viz import fvtk
    ren = fvtk.ren()
    ren.SetBackground(1, 1, 1.)

    if tubes:
        static_actor = fvtk.streamtube(static, fvtk.colors.red,
                                       linewidth=linewidth, opacity=opacity)
        moving_actor = fvtk.streamtube(moving, fvtk.colors.green,
                                       linewidth=linewidth, opacity=opacity)

    else:
        static_actor = fvtk.line(static, fvtk.colors.red,
                                 linewidth=linewidth, opacity=opacity)
        moving_actor = fvtk.line(moving, fvtk.colors.green,
                                 linewidth=linewidth, opacity=opacity)

    fvtk.add(ren, static_actor)
    fvtk.add(ren, moving_actor)

    fvtk.add(ren, fvtk.axes(scale=(2, 2, 2)))

    fvtk.show(ren, size=(900, 900))
    if fname is not None:
        fvtk.record(ren, size=(900, 900), out_path=fname)


def recognize_bundles_flow(streamline_files, model_bundle_files,
                           out_dir=None, load_clusters=False, clust_thr=15.,
                           reduction_thr=10, model_clust_thr=5.,
                           pruning_thr=5., slr=True, slr_metric=None,
                           slr_transform='similarity', slr_progressive=True,
                           slr_matrix='small', verbose=True,
                           disp=False, load_chunks=False, debug=False,
                           use_only=None):
    """ Recognize bundles

    Parameters
    ----------
    streamline_files : string
        The path of streamline files where you want to recognize bundles
    model_bundle_files : string
        The path of model bundle files
    out_dir : string, optional
        Directory to output the different files
    load_clusters : bool, optional
        Default False.
    clust_thr : float, optional
        MDF distance threshold for all streamlines
    reduction_thr : float, optional
        Reduce search space by (mm). (default 20)
    model_clust_thr : float, optional
        MDF distance threshold for the model bundles (default 5)
    pruning_thr : float, optional
        Pruning after matching (default 5).
    slr : bool, optional
        Enable local Streamline-based Linear Registration (default True).
    slr_metric : string, optional
        Options are None, static or sum (default None).
    slr_transform : string, optional
        Transformation allowed. translation, rigid, similarity or scaling
        (Default 'similarity').
    slr_progressive : bool, optional
        If for example you selected `rigid` in slr_transform then you will
        do first translation and then rigid (default True).
    slr_matrix : string, optional
        Options are 'nano', 'tiny', 'small', 'medium', 'large', 'huge' (default
        'small')
    verbose : bool, optional
        Enable standard output (defaut True).
    disp : bool, optional
        Show 3D results (default False).
    load_chunks : bool, optional
        Load streamlines in chunks (default False)
    debug : bool, optional
        Write out intremediate results (default False)
    use_only : int, optional
        Use only a random sample of the steamlines of size ``use_only``.
        Default is None which means that all the streamlines will be used.
    """

    if isinstance(streamline_files, string_types):
        sfiles = glob(streamline_files)
    else:
        raise ValueError('Streamline_files not a string')

    if isinstance(model_bundle_files, string_types):
        mbfiles = glob(model_bundle_files)
        if mbfiles == []:
            raise ValueError('Model_bundle_files is not correct')

    if out_dir is None:
        print('Results will be given in the same folder as input streamlines')

    bounds = [(-30, 30), (-30, 30), (-30, 30),
              (-45, 45), (-45, 45), (-45, 45),
              (0.8, 1.2), (0.8, 1.2), (0.8, 1.2)]

    slr_matrix = slr_matrix.lower()
    if slr_matrix == 'nano':
        slr_select = (100, 100)
    if slr_matrix == 'tiny':
        slr_select = (250, 250)
    if slr_matrix == 'small':
        slr_select = (400, 400)
    if slr_matrix == 'medium':
        slr_select = (600, 600)
    if slr_matrix == 'large':
        slr_select = (800, 800)
    if slr_matrix == 'huge':
        slr_select = (1200, 1200)

    slr_transform = slr_transform.lower()
    if slr_transform == 'translation':
        bounds = bounds[:3]
    if slr_transform == 'rigid':
        bounds = bounds[:6]
    if slr_transform == 'similarity':
        bounds = bounds[:7]
    if slr_transform == 'scaling':
        bounds = bounds[:9]

    print('### Recognition of bundles ###')

    print('# Streamline files')
    for sf in sfiles:
        print(sf)

        if not os.path.exists(sf):
            print('File {} does not exist'.format(sf))
            return

        t = time()
#        if not load_chunks:
#            streams, hdr = load_trk(sf)
#        else:
#            # HACK returning things as a generator
#            # this is processed in a different way now and in a specific bundle
#            streams, hdr = tv.read(sf, as_generator=True, points_space='rasmm')

        trkfile = nib.streamlines.load(sf)
        # print('Loading time {}'.format(time()-t))
        streamlines = trkfile.streamlines

        print(' Loading time %0.3f sec' % (time() - t,))

        #from ipdb import set_trace
        #set_trace()

#        sf_clusters = os.path.join(
#                os.path.dirname(sf),
#                os.path.splitext(os.path.basename(sf))[0] + '_clusters.pkl')

#        if bool(load_clusters) is True:
#            clusters = load_pickle(sf_clusters)
#        else:
#            clusters = None

        rb = RecoBundles(streamlines, None,
                         clust_thr=clust_thr,
                         load_chunks=load_chunks,
                         use_only=use_only)

#        if clusters is None:
#
#            print('Clusters of streamlines saved in \n {} '
#                  .format(sf_clusters))
#
#            rb.cluster_map.refdata = None
#            save_pickle(sf_clusters, rb.cluster_map)
#            rb.cluster_map.refdata = rb.streamlines

        print('# Model_bundle files')
        for mb in mbfiles:
            print(mb)

            if not os.path.exists(mb):
                print('File {} does not exist'.format(mb))
                return

            # model_bundle, hdr_model_bundle = load_trk(mb)
            model_trkfile = nib.streamlines.load(mb)

            model_bundle = model_trkfile.streamlines

            recognized_bundle = rb.recognize(
                model_bundle,
                model_clust_thr=float(model_clust_thr),
                reduction_thr=float(reduction_thr),
                slr=slr,
                slr_metric=slr_metric,
                slr_x0=slr_transform,
                slr_bounds=bounds,
                slr_select=slr_select,
                slr_method='L-BFGS-B',
                slr_use_centroids=False,
                slr_progressive=slr_progressive,
                pruning_thr=pruning_thr)

# TODO add option to return recognized bundle in the space that you want
# Or better return the labels of the bundle which I currently do.
#            extracted_bundle, mat2 = recognize_bundles(
#                model_bundle, moved_streamlines,
#                close_centroids_thr=close_centroids_thr,
#                clean_thr=clean_thr,
#                local_slr=local_slr,
#                expand_thr=expand_thr,
#                scale_range=scale_range,
#                verbose=verbose,
#                return_full=False)
#
#            extracted_bundle_initial = transform_streamlines(
#                extracted_bundle,
#                np.linalg.inv(np.dot(mat2, mat)))

            if disp:
                show_bundles(model_bundle, recognized_bundle)

            if out_dir is None:
                out_dir = ''

            sf_bundle_file = os.path.join(
                out_dir,
                os.path.basename(mb))

            sf_bundle_labels = os.path.join(
                out_dir,
                os.path.splitext(os.path.basename(mb))[0] + '_labels.npy')

            # if not os.path.exists(os.path.dirname(sf_bundle_file)):
            #     os.makedirs(os.path.dirname(sf_bundle_file))

            #save_trk(sf_bundle_file, recognized_bundle, hdr=hdr)

            recognized_tractogram = nib.streamlines.Tractogram(recognized_bundle)
            recognized_trkfile = nib.streamlines.TrkFile(recognized_tractogram)
            nib.streamlines.save(recognized_trkfile, sf_bundle_file)

            np.save(sf_bundle_labels, np.array(rb.labels))

            print('Recognized bundle saved in \n {} '
                  .format(sf_bundle_file))
            print('Recognized bundle labels saved in \n {} '
                  .format(sf_bundle_labels))

            if debug:
                sf_bundle_neighb = os.path.join(
                    out_dir,
                    os.path.splitext(os.path.basename(mb))[0] + '_neighb.trk')

                neighb_tractogram = nib.streamlines.Tractogram(
                    rb.neighb_streamlines)
                neighb_trkfile = nib.streamlines.TrkFile(neighb_tractogram)
                nib.streamlines.save(neighb_trkfile, sf_bundle_neighb)

                # save_trk(sf_bundle_neighb, rb.neighb_streamlines,
                #          hdr=hdr)
                print('Recognized bundle\'s neighbors saved in \n {} '
                      .format(sf_bundle_neighb))

        if debug:
            sf_centroids = os.path.join(
                os.path.dirname(sf),
                os.path.splitext(os.path.basename(sf))[0] + '_centroids.trk')

            centroid_tractogram = nib.streamlines.Tractogram(
                rb.centroids)
            centroid_trkfile = nib.streamlines.TrkFile(centroid_tractogram)
            nib.streamlines.save(centroid_trkfile, sf_centroids)

            # save_trk(sf_centroids, rb.centroids, hdr=hdr)
            print('Centroids of streamlines saved in \n {} '
                  .format(sf_centroids))


def kdtrees_bundles_flow(streamline_file, labels_file,
                         metric='mdf',
                         verbose=True):
    """ Expand reduce bundles using kdtrees

    Parameters
    ----------
    streamline_file : string
    labels_file : string
    metric : string
    verbose : bool, optional
        Print standard output (default True)
    """

    global bundle_actor
    global bundle
    global final_streamlines

    streamlines, hdr = load_trk(streamline_file)
    labels = np.load(labels_file)

    bundle = [streamlines[i] for i in labels]
    final_streamlines = bundle

    kdb = KDTreeBundles(streamlines, labels)
    kdb.build_kdtree(mam_metric=metric)

    from dipy.viz import window, actor, widget
    from dipy.data import fetch_viz_icons, read_viz_icons
    fetch_viz_icons()

    ren = window.Renderer()
    bundle_actor = actor.line(kdb.model_bundle)
    ren.add(bundle_actor)

    show_m = window.ShowManager(ren, size=(1200, 900))
    show_m.initialize()

    def expand_callback(obj, event):
        global bundle_actor
        global bundle
        global final_streamlines

        z = int(np.round(obj.get_value()))
        if z > len(bundle):
            dists, actual_indices, extra_streamlines = kdb.expand(z, True)
            final_streamlines = bundle + extra_streamlines
        if z < len(bundle):
            reduction = len(bundle) - z
            # print(reduction)
            dists, actual_indices, final_streamlines = kdb.reduce(reduction,
                                                                  True)
        if z == len(bundle):
            final_streamlines = bundle
        ren.rm(bundle_actor)
        bundle_actor = actor.line(final_streamlines)
        ren.add(bundle_actor)
        show_m.render()

    slider = widget.slider(show_m.iren, show_m.ren,
                           callback=expand_callback,
                           min_value=1,
                           max_value=len(bundle) + 10 * len(bundle),
                           value=len(bundle),
                           label="Expand/Reduce",
                           right_normalized_pos=(.98, 0.6),
                           size=(120, 0), label_format="%0.lf",
                           color=(1., 1., 1.),
                           selected_color=(0.86, 0.33, 1.))

    def button_save_callback(obj, event):
        global final_streamlines
        ftypes = (("Trackvis file", "*.trk"), ("All Files", "*.*"))
        fname = window.save_file_dialog(initial_file='dipy.trk',
                                        default_ext='.trk',
                                        file_types=ftypes)
        if fname != '':
            print('Saving new trk file ...')
            save_trk(fname, final_streamlines, hdr=hdr)
            print('File saved at ' + fname)

    button_png = read_viz_icons(fname='drive.png')
    button = widget.button(show_m.iren,
                           show_m.ren,
                           button_save_callback,
                           button_png, (.94, .9), (50, 50))

    global size
    size = ren.GetSize()

    def win_callback(obj, event):
        global size
        if size != obj.GetSize():

            slider.place(ren)
            button.place(ren)
            size = obj.GetSize()

    show_m.add_window_callback(win_callback)
    show_m.render()
    show_m.start()