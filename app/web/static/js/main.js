// Main JavaScript for NZB Indexer

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Auto-dismiss alerts after 5 seconds
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert-dismissible');
        alerts.forEach(function(alert) {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);

    // Toggle group active status in admin panel
    const groupToggleButtons = document.querySelectorAll('.toggle-group-status');
    if (groupToggleButtons) {
        groupToggleButtons.forEach(function(button) {
            button.addEventListener('click', async function(e) {
                e.preventDefault();
                const groupId = this.dataset.groupId;
                const currentStatus = this.dataset.status === 'true';

                try {
                    const response = await fetch(`/api/v1/groups/${groupId}`, {
                        method: 'PATCH',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            active: !currentStatus
                        })
                    });

                    if (response.ok) {
                        const data = await response.json();
                        // Update button state
                        this.dataset.status = data.active.toString();

                        // Update button text and class
                        if (data.active) {
                            this.textContent = 'Deactivate';
                            this.classList.remove('btn-success');
                            this.classList.add('btn-danger');
                        } else {
                            this.textContent = 'Activate';
                            this.classList.remove('btn-danger');
                            this.classList.add('btn-success');
                        }

                        // Update group item class
                        const groupItem = document.querySelector(`.group-item[data-group-id="${groupId}"]`);
                        if (groupItem) {
                            if (data.active) {
                                groupItem.classList.remove('inactive');
                            } else {
                                groupItem.classList.add('inactive');
                            }
                        }
                    } else {
                        console.error('Failed to update group status');
                    }
                } catch (error) {
                    console.error('Error updating group status:', error);
                }
            });
        });
    }
});
