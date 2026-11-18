extends RefCounted

const LABELS := {
	"Cut": "剪切", "Copy": "复制", "Paste": "粘贴", "Select All": "全选", "Clear": "清空",
	"Undo": "撤销", "Redo": "重做", "Indent": "缩进", "Unindent": "减少缩进",
	"Text Writing Direction": "文字书写方向",
	"Same as Layout Direction": "与界面方向一致",
	"Auto-Detect Direction": "自动判断方向",
	"Left-to-Right": "从左向右", "Right-to-Left": "从右向左",
	"Display Control Characters": "显示控制字符", "Insert Control Character": "插入控制字符",
	"Left-to-Right Mark (LRM)": "左至右标记（LRM）",
	"Right-to-Left Mark (RLM)": "右至左标记（RLM）",
	"Start of Left-to-Right Embedding (LRE)": "开始左至右嵌入（LRE）",
	"Start of Right-to-Left Embedding (RLE)": "开始右至左嵌入（RLE）",
	"Start of Left-to-Right Override (LRO)": "开始左至右覆盖（LRO）",
	"Start of Right-to-Left Override (RLO)": "开始右至左覆盖（RLO）",
	"Pop Direction Formatting (PDF)": "结束方向格式（PDF）",
	"Arabic Letter Mark (ALM)": "阿拉伯字母标记（ALM）",
	"Left-to-Right Isolate (LRI)": "左至右隔离（LRI）",
	"Right-to-Left Isolate (RLI)": "右至左隔离（RLI）",
	"First Strong Isolate (FSI)": "自动方向隔离（FSI）",
	"Pop Direction Isolate (PDI)": "结束方向隔离（PDI）",
	"Zero-Width Joiner (ZWJ)": "零宽连接符（ZWJ）",
	"Zero-Width Non-Joiner (ZWNJ)": "零宽非连接符（ZWNJ）",
	"Word Joiner (WJ)": "单词连接符（WJ）",
	"Soft Hyphen (SHY)": "软连字符（SHY）",
}


static func apply(menu: PopupMenu) -> void:
	_translate(menu)
	menu.about_to_popup.connect(_translate.bind(menu))


static func _translate(menu: PopupMenu) -> void:
	for index in menu.item_count:
		var label := menu.get_item_text(index)
		if LABELS.has(label):
			menu.set_item_text(index, LABELS[label])
	for child in menu.get_children():
		if child is PopupMenu:
			_translate(child)
