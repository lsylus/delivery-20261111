from b08_cases import assembly, params

from thermal_drawings.paint.batch import generate_batch
from thermal_drawings.paint.recommendations import recommend


def test_public_batch_input_generates_independent_group_results():
    model = assembly(features=True)
    recommendation = recommend(model, 'revision-1')
    groups = [group for group in recommendation['groups'] if group['recommended'] and group['selectable']]
    assert len(groups) >= 2
    target_groups = [{
        'group_id': group['group_id'],
        'instance_id': group['instance_id'],
        'instance_name': group['instance_name'],
        'direction_label': group['direction_label'],
        'normal': group['normal'],
        'side_label': group['side_label'],
        'paint_type': group['default_paint_type'],
        'target_face_refs': group['target_face_refs'],
    } for group in groups]
    value = params(model)
    value.update(
        target_face_groups=target_groups,
        target_face_refs=[ref for group in target_groups for ref in group['target_face_refs']],
        contact_offset_mm=3,
        hole_offset_mm=3,
        boss_additional_offset_mm=3,
    )
    result = generate_batch(value, model, 'revision-1')
    assert result['status'] in ('passed', 'needs_review')
    assert len(result['groups']) == len(target_groups)
    assert result['summary']['exportable'] >= 1
    assert all(item['paint'] is not None for item in result['groups'])
    assert all(item['paint']['drawing_document'] is not None for item in result['groups'] if item['status'] != 'failed')
