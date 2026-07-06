document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const chatHistory = document.getElementById('chat-history');
    
    // Configure marked to handle tables properly
    marked.setOptions({
        breaks: true,
        gfm: true
    });

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const message = userInput.value.trim();
        if (!message) return;
        
        await processMessage(message);
    });
    
    // Expose for quick action buttons
    window.startAnalysis = async (message) => {
        await processMessage(message);
    };

    async function processMessage(message) {
        // Clear input
        userInput.value = '';
        userInput.disabled = true;
        sendBtn.disabled = true;
        
        // Reset agent activity steps
        resetAgentSteps();

        // Add user message to UI
        appendMessage(message, 'user');

        // Prepare agent message container
        const agentMessageDiv = createAgentMessageContainer();
        chatHistory.appendChild(agentMessageDiv);
        scrollToBottom();

        // Update UI state
        setAgentState('active', 'エージェントが思考中...');

        try {
            // Setup SSE
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    message: message,
                    session_id: 'session-' + Date.now() 
                })
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let fullMarkdown = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const dataStr = line.slice(6);
                        if (!dataStr) continue;

                        try {
                            const data = JSON.parse(dataStr);
                            
                            if (data.type === 'message') {
                                fullMarkdown += data.content;
                                // Parse markdown and update
                                agentMessageDiv.querySelector('.message-content').innerHTML = marked.parse(fullMarkdown);
                                scrollToBottom();
                            } else if (data.type === 'status') {
                                setAgentState('active', data.content);
                                updateSteps(data.content);
                            } else if (data.type === 'error') {
                                console.error('Server error:', data.content);
                                setAgentState('waiting', 'エラーが発生しました');
                            } else if (data.type === 'done') {
                                setAgentState('waiting', '✅ 分析完了');
                                updateSteps('完了', true);
                            }
                        } catch (e) {
                            console.error('Error parsing SSE data:', e, dataStr);
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Fetch error:', error);
            agentMessageDiv.querySelector('.message-content').innerHTML = '<span style="color:var(--danger)">エラーが発生しました。サーバーが起動しているか確認してください。</span>';
            setAgentState('waiting', 'エラー');
        } finally {
            userInput.disabled = false;
            sendBtn.disabled = false;
            userInput.focus();
        }
    }

    function appendMessage(text, sender) {
        const div = document.createElement('div');
        div.className = `message ${sender}-message`;
        div.innerHTML = `<div class="message-content">${escapeHTML(text)}</div>`;
        chatHistory.appendChild(div);
        scrollToBottom();
    }

    function createAgentMessageContainer() {
        const div = document.createElement('div');
        div.className = 'message agent-message';
        div.innerHTML = '<div class="message-content"><div class="typing-indicator">分析しています...</div></div>';
        return div;
    }

    function scrollToBottom() {
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    function escapeHTML(str) {
        return str.replace(/[&<>'"]/g, 
            tag => ({
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                "'": '&#39;',
                '"': '&quot;'
            }[tag] || tag)
        );
    }

    const steps = [
        "リクエストの解析",
        "JPXから銘柄リスト取得",
        "yfinanceから市場データ取得",
        "流通時価総額の計算",
        "年間売買代金回転率の計算",
        "採用候補のスクリーニング",
        "レポート生成"
    ];
    let currentStepIndex = 0;

    function setAgentState(state, text) {
        const statusText = document.getElementById('agent-status-text');
        const progressBar = document.getElementById('agent-progress');
        
        statusText.textContent = text;
        statusText.className = `status-text ${state}`;
        
        if (state === 'active') {
            progressBar.classList.add('loading');
            progressBar.style.width = '100%';
        } else {
            progressBar.classList.remove('loading');
            progressBar.style.width = '0%';
        }
    }

    function updateSteps(statusText, isDone = false) {
        const stepsContainer = document.getElementById('agent-steps');
        
        // 1. Initialize steps on first call
        if (stepsContainer.children.length === 0) {
            steps.forEach((step, index) => {
                const li = document.createElement('li');
                li.className = 'step';
                li.id = `step-${index}`;
                li.innerHTML = `<span class="step-icon">○</span> <span class="step-text">${step}</span>`;
                stepsContainer.appendChild(li);
            });
        }

        if (isDone) {
            // Mark all steps as completed to ensure the final step gets checked
            for (let i = 0; i < steps.length; i++) {
                const li = document.getElementById(`step-${i}`);
                if (li) {
                    li.className = 'step completed';
                    li.querySelector('.step-icon').textContent = '✓';
                }
            }
            // Remove any temporary database rebuilding step if present
            const dbStep = document.getElementById('step-db-rebuild');
            if (dbStep) {
                dbStep.className = 'step completed';
                dbStep.querySelector('.step-icon').textContent = '✓';
            }
            return;
        }

        // 2. Handle temporary database rebuilding step
        if (statusText.includes("データベース") || statusText.includes("再構築")) {
            let dbStep = document.getElementById('step-db-rebuild');
            if (!dbStep) {
                dbStep = document.createElement('li');
                dbStep.className = 'step active';
                dbStep.id = 'step-db-rebuild';
                dbStep.innerHTML = `<span class="step-icon">▶</span> <span class="step-text" style="color: var(--accent-light); font-weight: 500;">データベース初期構築中 (約60秒〜90秒)</span>`;
                // Insert at the very top of stepsContainer
                stepsContainer.insertBefore(dbStep, stepsContainer.firstChild);
            } else {
                dbStep.className = 'step active';
                dbStep.querySelector('.step-icon').textContent = '▶';
            }
            return;
        }

        // If we transition to standard steps, make sure to check off the database rebuilding step if it was active
        const dbStep = document.getElementById('step-db-rebuild');
        if (dbStep && dbStep.className.includes('active') && !statusText.includes("データベース")) {
            dbStep.className = 'step completed';
            dbStep.querySelector('.step-icon').textContent = '✓';
        }

        // 3. Map statusText to specific steps
        let activeIndex = -1;
        if (statusText.includes("解析中")) {
            activeIndex = 0;
        } else if (statusText.includes("JPX") || statusText.includes("銘柄リスト")) {
            activeIndex = 1;
        } else if (statusText.includes("市場データ") || statusText.includes("ロード中")) {
            activeIndex = 2;
        } else if (statusText.includes("流通時価総額")) {
            activeIndex = 3;
        } else if (statusText.includes("年間売買代金") || statusText.includes("回転率")) {
            activeIndex = 4;
        } else if (statusText.includes("スクリーニング") || statusText.includes("候補")) {
            activeIndex = 5;
        } else if (statusText.includes("レポート") || statusText.includes("生成中")) {
            activeIndex = 6;
        }

        // 4. Update the visual classes of the steps on the UI
        if (activeIndex !== -1) {
            for (let i = 0; i < steps.length; i++) {
                const li = document.getElementById(`step-${i}`);
                if (li) {
                    if (i < activeIndex) {
                        li.className = 'step completed';
                        li.querySelector('.step-icon').textContent = '✓';
                    } else if (i === activeIndex) {
                        li.className = 'step active';
                        li.querySelector('.step-icon').textContent = '▶';
                    } else {
                        li.className = 'step';
                        li.querySelector('.step-icon').textContent = '○';
                    }
                }
            }
        }
    }

    function resetAgentSteps() {
        const stepsContainer = document.getElementById('agent-steps');
        if (stepsContainer) {
            stepsContainer.innerHTML = '';
        }
        currentStepIndex = 0;
    }
});
