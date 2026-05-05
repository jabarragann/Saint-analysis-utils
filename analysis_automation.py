import os
import vtk
import slicer
from pathlib import Path

#
# ---- USER INPUTS ----
#
BASE_DIR = Path(os.getcwd()) / "data"  # adjust as needed

POST_SEG_PATH = os.path.join(BASE_DIR, "phantom01_0_Loop_x_post_seg.seg.nrrd")
PRE_SEG_PATH  = os.path.join(BASE_DIR, "phantom01_0_Loop_x_pre_seg.seg.nrrd")

POST_MRK_PATH = os.path.join(BASE_DIR, "post.mrk.json")
PRE_MRK_PATH  = os.path.join(BASE_DIR, "pre.mrk.json")

OUTPUT_DIR = Path("./output")
OUTPUT_DIR.mkdir(exist_ok=True)

POST_MESH_PATH = os.path.join(OUTPUT_DIR, "post_aligned.ply")
PRE_MESH_PATH  = os.path.join(OUTPUT_DIR, "pre.ply")
TRANSFORM_PATH = os.path.join(OUTPUT_DIR, "post2pre.h5")

#
# ---- HELPERS ----
#

def load_segmentation(path):
    node = slicer.util.loadSegmentation(path)
    if node is None:
        raise RuntimeError(f"Failed to load segmentation: {path}")
    return node

def load_markups(path):
    node = slicer.util.loadMarkups(path)
    if node is None:
        raise RuntimeError(f"Failed to load markups: {path}")
    return node

def markups_to_vtk_points(markupsNode):
    pts = vtk.vtkPoints()
    n = markupsNode.GetNumberOfControlPoints()
    for i in range(n):
        p = [0.0, 0.0, 0.0]
        markupsNode.GetNthControlPointPosition(i, p)
        pts.InsertNextPoint(p)
    return pts

def compute_rigid_transform(sourcePts, targetPts):
    transform = vtk.vtkLandmarkTransform()
    transform.SetSourceLandmarks(sourcePts)
    transform.SetTargetLandmarks(targetPts)
    transform.SetModeToRigidBody()
    transform.Update()
    return transform

def compute_errors(transform, sourcePts, targetPts):
    n = sourcePts.GetNumberOfPoints()
    errors = []
    total_sq = 0.0

    for i in range(n):
        src = sourcePts.GetPoint(i)
        tgt = targetPts.GetPoint(i)

        transformed = transform.TransformPoint(src)
        dist = vtk.vtkMath.Distance2BetweenPoints(transformed, tgt) ** 0.5

        errors.append(dist)
        total_sq += dist**2

    rmse = (total_sq / n) ** 0.5
    return rmse, errors

def segmentation_to_merged_model(segNode, modelName="MergedModel"):
    shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
    exportFolderItemId = shNode.CreateFolderItem(shNode.GetSceneItemID(), modelName)

    slicer.modules.segmentations.logic().ExportAllSegmentsToModels(
        segNode, exportFolderItemId
    )

    # collect all model nodes
    children = vtk.vtkIdList()
    shNode.GetItemChildren(exportFolderItemId, children)

    append = vtk.vtkAppendPolyData()

    for i in range(children.GetNumberOfIds()):
        itemId = children.GetId(i)
        modelNode = shNode.GetItemDataNode(itemId)
        if modelNode:
            poly = modelNode.GetPolyData()
            if poly:
                append.AddInputData(poly)

    append.Update()

    cleaner = vtk.vtkCleanPolyData()
    cleaner.SetInputConnection(append.GetOutputPort())
    cleaner.Update()

    mergedModel = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", modelName)
    mergedModel.SetAndObservePolyData(cleaner.GetOutput())

    return mergedModel

def save_model(node, path):
    slicer.util.saveNode(node, path)

def save_transform(vtkTransform, path):
    tnode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTransformNode", "post2pre")
    tnode.SetAndObserveTransformToParent(vtkTransform)
    slicer.util.saveNode(tnode, path)
    return tnode

def main():

    print("Loading data...")

    postSeg = load_segmentation(POST_SEG_PATH)
    preSeg  = load_segmentation(PRE_SEG_PATH)

    postMrk = load_markups(POST_MRK_PATH)
    preMrk  = load_markups(PRE_MRK_PATH)

    if postMrk.GetNumberOfControlPoints() != preMrk.GetNumberOfControlPoints():
        raise RuntimeError("Mismatch in number of landmarks (post vs pre)")

    print("Converting landmarks to VTK points...")

    postPts = markups_to_vtk_points(postMrk)
    prePts  = markups_to_vtk_points(preMrk)

    print("Computing rigid transform (post → pre)...")

    vtkTransform = compute_rigid_transform(postPts, prePts)

    rmse, errors = compute_errors(vtkTransform, postPts, prePts)

    print("\n=== Registration Error ===")
    print(f"RMSE: {rmse:.4f} mm")
    for i, e in enumerate(errors):
        print(f"Point {i}: {e:.4f} mm")

    print("\nSaving transform...")
    transformNode = save_transform(vtkTransform, TRANSFORM_PATH)

    print("Applying transform to POST segmentation...")

    postSeg.SetAndObserveTransformNodeID(transformNode.GetID())
    slicer.vtkSlicerTransformLogic().hardenTransform(postSeg)

    print("Converting segmentations to merged surfaces...")

    postModel = segmentation_to_merged_model(postSeg, "PostMerged")
    preModel  = segmentation_to_merged_model(preSeg, "PreMerged")

    print("Saving meshes...")

    save_model(postModel, POST_MESH_PATH)
    save_model(preModel, PRE_MESH_PATH)

    print("\nDone.")
    print(f"- Post aligned mesh: {POST_MESH_PATH}")
    print(f"- Pre mesh:          {PRE_MESH_PATH}")
    print(f"- Transform:         {TRANSFORM_PATH}")

    # exit slicer cleanly
    slicer.util.exit()

if __name__ == "__main__":
    main()

