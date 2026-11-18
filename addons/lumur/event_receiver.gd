class_name LumurEventReceiver
extends Node

## Listens for companion room-input events over local UDP JSON (ADR 0014).
## Envelope: ``{"schema":"lumur.event","schema_version":"1.0","event":{...}}``.

signal footstep(event: Dictionary)
signal raw_event(event: Dictionary)

@export var bind_host: String = "127.0.0.1"
@export var bind_port: int = 8765
@export var auto_listen: bool = true

var _peer: PacketPeerUDP
var _listening: bool = false


func _ready() -> void:
	if auto_listen:
		listen()


func _process(_delta: float) -> void:
	if not _listening or _peer == null:
		return
	while _peer.get_available_packet_count() > 0:
		var packet := _peer.get_packet()
		_handle_packet(packet)


func listen(port: int = -1) -> Error:
	if port > 0:
		bind_port = port
	_peer = PacketPeerUDP.new()
	var err := _peer.bind(bind_port, bind_host)
	if err != OK:
		push_error("LumurEventReceiver: bind failed on %s:%d (%s)" % [bind_host, bind_port, err])
		_listening = false
		return err
	_listening = true
	return OK


func stop() -> void:
	_listening = false
	if _peer != null:
		_peer.close()
		_peer = null


func _handle_packet(packet: PackedByteArray) -> void:
	var text := packet.get_string_from_utf8().strip_edges()
	if text.is_empty():
		return
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		return
	var doc: Dictionary = parsed
	if str(doc.get("schema", "")) != "lumur.event":
		return
	var event: Variant = doc.get("event", {})
	if typeof(event) != TYPE_DICTIONARY:
		return
	var ev: Dictionary = event
	raw_event.emit(ev)
	if str(ev.get("type", "")) == "footstep":
		footstep.emit(ev)


func inject_event_json(text: String) -> void:
	## Test helper: feed a datagram without the network.
	_handle_packet(text.to_utf8_buffer())
