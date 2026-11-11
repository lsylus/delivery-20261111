// Local evaluation using QCAD's public document and editing API.
// No DXF bridge, generated replacement drawing or trial modification is used.
include("scripts/library.js");
include("scripts/Tools/arguments.js");

function point(v) { return [v.x, v.y]; }
function snapshot(doc) {
    var items = [];
    var ids = doc.queryAllEntities();
    for (var i=0; i<ids.length; i++) {
        var e = doc.queryEntity(ids[i]);
        if (e.getBlockId() !== doc.getModelSpaceBlockId()) continue;
        var b = e.getBoundingBox();
        var item = {id:e.getId(), type:e.getType(), layer:doc.queryLayer(e.getLayerId()).getName(),
                    bounds:[point(b.getMinimum()),point(b.getMaximum())]};
        if (isPolylineEntity(e)) {
            item.kind = "polyline";
            item.vertices = [];
            for (var j=0; j<e.countVertices(); j++) item.vertices.push(point(e.getVertexAt(j)));
            item.closed = e.isClosed();
        }
        else if (isDimensionEntity(e)) { item.kind="dimension"; item.text=e.getText(); item.measurement=e.getMeasurement(); }
        else if (isTextEntity(e)) { item.kind="text"; item.text=e.getPlainText(); }
        else if (isHatchEntity(e)) { item.kind="hatch"; }
        else if (isCircleEntity(e)) { item.kind="circle"; item.radius=e.getRadius(); }
        else if (isArcEntity(e)) { item.kind="arc"; item.radius=e.getRadius(); }
        else if (isLineEntity(e)) { item.kind="line"; }
        else if (isPointEntity(e)) { item.kind="point"; }
        items.push(item);
    }
    return {unit:doc.getUnit(),entities:items};
}

function main() {
    var input = args[args.length-2];
    var output = args[args.length-1];
    var result = {software:"QCAD Professional", version:RSettings.getVersionString(),
                  input:input, output:output, status:"failed", backend:"QCAD DWG plugin (ODA libraries)",
                  autocad_verified:false};
    try {
        var doc = new RDocument(new RMemoryStorage(),new RSpatialIndexSimple());
        var di = new RDocumentInterface(doc);
        if (di.importFile(input)!==RDocumentInterface.IoErrorNoError) throw "DWG import failed";
        result.before = snapshot(doc);
        var ids=doc.queryAllEntities();
        var contours=0, dimensions=0;
        var operation=new RModifyObjectsOperation();
        for (var i=0;i<ids.length;i++) {
            var e=doc.queryEntity(ids[i]);
            if (e.getBlockId()!==doc.getModelSpaceBlockId()) continue;
            var layer=doc.queryLayer(e.getLayerId()).getName();
            if (isPolylineEntity(e) && layer==="OUTLINE") {
                if (e.countVertices()!==4 || !e.isClosed()) throw "unexpected outline";
                e.setVertexAt(1,new RVector(101,0));
                e.setVertexAt(2,new RVector(101,60));
                operation.addObject(e,false); contours++;
            }
            if (isDimensionEntity(e) && e.getText()==="60 mm") {
                e.setText("60 mm - B04 edited");
                operation.addObject(e,false); dimensions++;
            }
        }
        if (contours!==1 || dimensions!==1) throw "editable contour/dimension not uniquely identified";
        di.applyOperation(operation);
        result.after_edit=snapshot(doc);
        result.save_return=di.exportFile(output,"R32 (2018) DWG");
        if (!result.save_return) throw "DWG save failed";
        // A fresh document interface forces an independent reopen from disk.
        di.destroy();
        var reopened=new RDocument(new RMemoryStorage(),new RSpatialIndexSimple());
        var reader=new RDocumentInterface(reopened);
        if (reader.importFile(output)!==RDocumentInterface.IoErrorNoError) throw "edited DWG reopen failed";
        result.after_reopen=snapshot(reopened);
        result.status="executed_pending_validation";
        reader.destroy();
    } catch (error) { result.error=String(error); }
    print("B04_QCAD_RESULT="+JSON.stringify(result));
}
main();
