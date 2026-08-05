from src.socket_region_detector import socket_crops


def test_socket_crops_select_only_socket_regions():
    verification={'region_crops':[
        {'name':'cpu_socket','crop':'socket.jpg'},
        {'name':'dimm_slots','crop':'ram.jpg'},
        {'name':'processor_socket','crop':'socket2.jpg'},
    ]}
    assert [row['crop'] for row in socket_crops(verification)]==['socket.jpg','socket2.jpg']
