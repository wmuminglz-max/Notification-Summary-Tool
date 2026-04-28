let currentFiles = [];
let chatHistory = [];
let currentSourceContent = '';
let currentSummary = '';
let currentResultText = '';
let currentResultType = 'summary';
let todoCheckState = {};
let currentFileNames = [];
let currentUserRole = '普通学生';
let currentSourceCount = 0;

const uploadArea = document.getElementById('uploadArea');

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

function renderInlineMarkdown(text) {
    let html = escapeHtml(text == null ? '' : String(text));

    html = html
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/__([^_]+)__/g, '<strong>$1</strong>')
        .replace(/(^|[^*])\*([^*]+)\*(?!\*)/g, '$1<em>$2</em>')
        .replace(/(^|[^_])_([^_]+)_(?!_)/g, '$1<em>$2</em>')
        .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

    return html;
}

document.addEventListener('DOMContentLoaded', () => {
    const roleSelect = document.getElementById('userRole');
    if (roleSelect) {
        currentUserRole = roleSelect.value || '普通学生';
        roleSelect.addEventListener('change', () => {
            currentUserRole = roleSelect.value || '普通学生';
        });
    }
    checkConfig();
});

async function checkConfig() {
    try {
        const response = await fetch('/api/config');
        const data = await response.json();
        if (!data.has_api_key) {
            toggleSettings();
        }
    } catch (error) {
        console.error('检查配置失败:', error);
    }
}

function toggleSettings() {
    const content = document.getElementById('settingsContent');
    content.classList.toggle('active');
}

async function saveSettings() {
    const apiKey = document.getElementById('apiKey').value;
    const model = document.getElementById('model').value;

    if (!apiKey) {
        alert('请输入 API Key');
        return;
    }

    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey, model })
        });

        const data = await response.json();
        if (data.success) {
            alert('配置已保存！');
            toggleSettings();
        } else {
            alert('保存失败: ' + (data.error || '未知错误'));
        }
    } catch (error) {
        alert('保存失败: ' + error.message);
    }
}

function mergeFiles(fileList) {
    const validTypes = ['pdf', 'doc', 'docx', 'txt'];
    const existingKeys = new Set(currentFiles.map(file => `${file.name}_${file.size}_${file.lastModified}`));
    const added = [];

    Array.from(fileList || []).forEach(file => {
        const ext = (file.name.split('.').pop() || '').toLowerCase();
        const key = `${file.name}_${file.size}_${file.lastModified}`;
        if (validTypes.includes(ext) && !existingKeys.has(key)) {
            currentFiles.push(file);
            existingKeys.add(key);
            added.push(file.name);
        }
    });

    renderFilePreview();
    if (!added.length && fileList && fileList.length) {
        showError('未添加新文件：请确认文件格式正确，且未重复上传');
    }
}

function handleFileSelect(event) {
    mergeFiles(event.target.files);
    event.target.value = '';
}

function renderFilePreview() {
    const placeholder = document.querySelector('.upload-placeholder');
    const list = document.getElementById('filePreviewList');
    if (!currentFiles.length) {
        placeholder.style.display = 'block';
        list.style.display = 'none';
        list.innerHTML = '';
        return;
    }

    placeholder.style.display = 'none';
    list.style.display = 'flex';
    list.innerHTML = currentFiles.map((file, index) => `
        <div class="file-preview">
            <i class="fas fa-file"></i>
            <span title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span>
            <button class="remove-btn" onclick="removeFile(${index})">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `).join('');
}

function removeFile(index = null) {
    if (index === null) {
        currentFiles = [];
    } else {
        currentFiles.splice(index, 1);
    }
    document.getElementById('fileInput').value = '';
    renderFilePreview();
}

function setLoading(visible, text = '正在处理中，请稍候...') {
    document.getElementById('loading').style.display = visible ? 'block' : 'none';
    document.getElementById('loadingText').textContent = text;
    if (visible) {
        document.getElementById('resultContainer').style.display = 'none';
        document.getElementById('errorContainer').style.display = 'none';
    }
}

async function summarize() {
    const text = document.getElementById('notificationText').value;
    if (!text.trim() && !currentFiles.length) {
        showError('请输入通知内容或上传文件');
        return;
    }

    setLoading(true, currentFiles.length > 1 ? '正在汇总多份通知并生成摘要...' : '正在生成摘要...');

    try {
        const formData = new FormData();
        currentFiles.forEach(file => formData.append('files', file));
        formData.append('text', text);
        formData.append('user_role', currentUserRole);

        const response = await fetch('/api/summarize', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (data.success) {
            currentSourceContent = data.source_content || text || '';
            currentSummary = data.result || '';
            currentResultType = 'summary';
            currentResultText = currentSummary;
            currentFileNames = data.file_names || currentFiles.map(file => file.name);
            currentSourceCount = Number(data.source_count || 0);
            currentUserRole = data.user_role || currentUserRole;
            todoCheckState = {};
            showResult(currentSummary, 'summary');
            if (!chatHistory.length) {
                const msg = currentFileNames.length > 1
                    ? `我已经按“${currentUserRole}”身份读取 ${currentFileNames.length} 份通知了，你可以继续追问，或直接点“整理为待办”。`
                    : `我已经按“${currentUserRole}”身份读取当前通知内容了，你可以继续追问，或直接点“整理为待办”。`;
                addChatMessage('assistant', msg);
            }
        } else {
            showError(data.error || '处理失败');
        }
    } catch (error) {
        showError('请求失败: ' + error.message);
    } finally {
        setLoading(false);
    }
}

async function generateTodo() {
    const text = document.getElementById('notificationText').value.trim();
    const sourceContent = currentSourceContent || text;

    if (!sourceContent && !currentSummary && !chatHistory.length) {
        showError('请先输入通知内容，或先生成摘要');
        return;
    }

    setLoading(true, '正在按截止时间整理待办...');

    try {
        const response = await fetch('/api/todo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_content: sourceContent,
                summary: currentSummary,
                history: chatHistory,
                user_role: currentUserRole
            })
        });
        const data = await response.json();

        if (data.success) {
            currentResultType = 'todo';
            currentResultText = data.result || '';
            todoCheckState = {};
            showResult(currentResultText, 'todo');
        } else {
            showError(data.error || '待办整理失败');
        }
    } catch (error) {
        showError('请求失败: ' + error.message);
    } finally {
        setLoading(false);
    }
}

function renderMarkdownLike(result) {
    const lines = String(result || '').split(/\r?\n/);
    let html = lines.map(line => {
        if (/^##\s+/.test(line)) {
            return `<h2>${renderInlineMarkdown(line.replace(/^##\s+/, ''))}</h2>`;
        }
        if (/^-\s+/.test(line)) {
            return `<li>${renderInlineMarkdown(line.replace(/^-\s+/, ''))}</li>`;
        }
        const orderedMatch = line.match(/^(\d+)\.\s+(.+)$/);
        if (orderedMatch) {
            return `<li>${orderedMatch[1]}. ${renderInlineMarkdown(orderedMatch[2])}</li>`;
        }
        return renderInlineMarkdown(line);
    }).join('\n');

    return html
        .replace(/(<li>.*?<\/li>\n?)+/gs, match => `<ul>${match}</ul>`)
        .replace(/\n/g, '<br>');
}

function parseTodoText(result) {
    const lines = String(result || '').split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    const sections = [];
    let currentSection = null;

    const getSection = (title) => {
        let section = sections.find(item => item.title === title);
        if (!section) {
            section = { title, items: [] };
            sections.push(section);
        }
        return section;
    };

    lines.forEach(line => {
        const headingMatch = line.match(/^##\s+(.+)$/);
        if (headingMatch) {
            currentSection = getSection(headingMatch[1]);
            return;
        }

        const bulletMatch = line.match(/^(?:-\s+\[[ xX]\]\s+|-\s+|\d+\.\s+)(.+)$/);
        if (bulletMatch) {
            if (!currentSection) currentSection = getSection('未分类');
            currentSection.items.push(bulletMatch[1].trim());
            return;
        }

        if (/^今天[：:]/.test(line)) {
            const section = getSection('📅 今天');
            const content = line.replace(/^今天[：:]/, '').trim();
            if (content && content !== '无' && content !== '暂无') section.items.push(content);
            return;
        }

        if (/^本周[：:]/.test(line)) {
            const section = getSection('🗓️ 本周');
            const content = line.replace(/^本周[：:]/, '').trim();
            if (content && content !== '无' && content !== '暂无') section.items.push(content);
            return;
        }

        if (/^(截止日前|截止前)[：:]/.test(line)) {
            const section = getSection('⏳ 截止前');
            const content = line.replace(/^(截止日前|截止前)[：:]/, '').trim();
            if (content && content !== '无' && content !== '暂无') section.items.push(content);
            return;
        }

        if (line.startsWith('-')) {
            if (!currentSection) currentSection = getSection('未分类');
            currentSection.items.push(line.replace(/^-/,'').trim());
            return;
        }

        if (!currentSection) currentSection = getSection('补充说明');
        currentSection.items.push(line);
    });

    const aliasMap = {
        '✅ 总待办清单': '🧾 总待办',
        '📅 时间安排': '📅 时间安排',
        '今天': '📅 今天',
        '本周': '🗓️ 本周',
        '截止前': '⏳ 截止前',
        '截止日前': '⏳ 截止前'
    };

    sections.forEach(section => {
        section.title = aliasMap[section.title] || section.title;
    });

    const grouped = [];
    const preferredOrder = ['🧾 总待办', '🚨 高优先级', '📅 今天', '🗓️ 本周', '⏳ 截止前', '🧰 所需材料/动作', '⚠️ 风险与注意事项', '补充说明', '未分类'];
    preferredOrder.forEach(title => {
        const section = sections.find(item => item.title === title && item.items.length);
        if (section) grouped.push(section);
    });
    sections.forEach(section => {
        if (!grouped.includes(section) && section.items.length) grouped.push(section);
    });

    return grouped;
}

function renderTodoStructured(result) {
    const sections = parseTodoText(result);
    if (!sections.length) return renderMarkdownLike(result);

    return sections.map((section, sectionIndex) => {
        const itemsHtml = section.items.map((item, itemIndex) => {
            const key = `${section.title}-${sectionIndex}-${itemIndex}-${item}`;
            const checked = Boolean(todoCheckState[key]);
            return `
                <label class="todo-check-item ${checked ? 'checked' : ''}">
                    <input type="checkbox" data-todo-key="${escapeHtml(key)}" ${checked ? 'checked' : ''} onchange="toggleTodoItem(this)">
                    <span>${renderInlineMarkdown(item)}</span>
                </label>
            `;
        }).join('');

        return `
            <div class="todo-group">
                <div class="todo-group-title">${escapeHtml(section.title)}</div>
                <div class="todo-group-items">${itemsHtml}</div>
            </div>
        `;
    }).join('');
}

function updateTodoProgress() {
    const wrapper = document.getElementById('resultMeta');
    if (!wrapper) return;
    const checkboxes = Array.from(document.querySelectorAll('#resultContent input[type="checkbox"][data-todo-key]'));
    const sourceInfo = currentSourceCount ? `<div class="todo-file-count">来源数 ${currentSourceCount}</div>` : (currentFileNames.length ? `<div class="todo-file-count">文件数 ${currentFileNames.length}</div>` : '');
    if (!checkboxes.length) {
        wrapper.innerHTML = sourceInfo;
        return;
    }
    const checked = checkboxes.filter(item => item.checked).length;
    wrapper.innerHTML = `${sourceInfo}<div class="todo-progress">已完成 ${checked} / ${checkboxes.length}</div>`;
}

function toggleTodoItem(checkbox) {
    const key = checkbox.dataset.todoKey;
    todoCheckState[key] = checkbox.checked;
    const item = checkbox.closest('.todo-check-item');
    if (item) item.classList.toggle('checked', checkbox.checked);
    updateTodoProgress();
}

function showResult(result, type = 'summary') {
    const container = document.getElementById('resultContainer');
    const content = document.getElementById('resultContent');
    const copyBtn = document.querySelector('.copy-btn');

    currentResultText = result || '';
    currentResultType = type;

    if (type === 'todo') {
        content.innerHTML = renderTodoStructured(result);
        if (copyBtn) copyBtn.innerHTML = '<i class="fas fa-copy"></i> 一键复制待办';
    } else {
        content.innerHTML = renderMarkdownLike(result);
        if (copyBtn) copyBtn.innerHTML = '<i class="fas fa-copy"></i> 一键复制';
    }

    container.style.display = 'block';
    document.getElementById('errorContainer').style.display = 'none';
    updateTodoProgress();
}

function showError(message) {
    const container = document.getElementById('errorContainer');
    document.getElementById('errorMessage').textContent = message;
    container.style.display = 'flex';
}

function clearAll() {
    document.getElementById('notificationText').value = '';
    document.getElementById('resultContainer').style.display = 'none';
    document.getElementById('errorContainer').style.display = 'none';
    document.getElementById('chatMessages').innerHTML = '';
    document.getElementById('chatInput').value = '';
    const resultMeta = document.getElementById('resultMeta');
    if (resultMeta) resultMeta.innerHTML = '';
    removeFile();
    chatHistory = [];
    currentSourceContent = '';
    currentSummary = '';
    currentResultText = '';
    currentResultType = 'summary';
    todoCheckState = {};
    currentFileNames = [];
    currentSourceCount = 0;
    const roleSelect = document.getElementById('userRole');
    if (roleSelect) {
        roleSelect.value = '普通学生';
        currentUserRole = roleSelect.value;
    }
}

function buildCopyText() {
    if (currentResultType !== 'todo') {
        return document.getElementById('resultContent').innerText;
    }

    const sections = parseTodoText(currentResultText);
    return sections.map((section, sectionIndex) => {
        const lines = [section.title];
        section.items.forEach((item, itemIndex) => {
            const key = `${section.title}-${sectionIndex}-${itemIndex}-${item}`;
            const mark = todoCheckState[key] ? '[x]' : '[ ]';
            lines.push(`- ${mark} ${item}`);
        });
        return lines.join('\n');
    }).join('\n\n');
}

function copyResult() {
    const content = buildCopyText();
    navigator.clipboard.writeText(content).then(() => {
        const btn = document.querySelector('.copy-btn');
        const originalText = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-check"></i> 已复制';
        setTimeout(() => {
            btn.innerHTML = originalText;
        }, 2000);
    });
}

function downloadResult() {
    const content = buildCopyText();
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = '通知整理_' + new Date().toISOString().slice(0, 10) + '.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

async function sendMessage() {
    const input = document.getElementById('chatInput');
    const message = input.value.trim();
    if (!message) return;

    addChatMessage('user', message);
    input.value = '';
    chatHistory.push({ role: 'user', content: message });

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message,
                history: chatHistory.slice(0, -1),
                source_content: currentSourceContent || document.getElementById('notificationText').value,
                summary: currentSummary,
                user_role: currentUserRole
            })
        });

        const data = await response.json();
        if (data.success) {
            addChatMessage('assistant', data.response);
            chatHistory.push({ role: 'assistant', content: data.response });
        } else {
            addChatMessage('assistant', '抱歉，出现错误: ' + data.error);
        }
    } catch (error) {
        addChatMessage('assistant', '抱歉，请求失败: ' + error.message);
    }
}

function addChatMessage(role, content) {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'message ' + role;
    div.textContent = content;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function handleChatKeypress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.style.borderColor = 'var(--primary-color)';
    uploadArea.style.background = 'rgba(255, 107, 53, 0.05)';
});

uploadArea.addEventListener('dragleave', (e) => {
    e.preventDefault();
    uploadArea.style.borderColor = 'var(--border-color)';
    uploadArea.style.background = 'transparent';
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.style.borderColor = 'var(--border-color)';
    uploadArea.style.background = 'transparent';
    mergeFiles(e.dataTransfer.files);
});
