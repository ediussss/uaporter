using System;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;

namespace UAPorter.Runtime
{
    /// <summary>
    /// Injected Touch Control Manager for Mobile ports.
    /// Provides virtual joysticks and touch buttons with automatic controller auto-hide.
    /// </summary>
    public class TouchManager : MonoBehaviour
    {
        private static TouchManager _instance;
        public static TouchManager Instance => _instance;

        [Header("UI Overlay Canvas")]
        public Canvas overlayCanvas;
        public RectTransform joystickArea;
        public RectTransform actionButtonsArea;

        [Header("Configuration")]
        public bool hideWhenControllerConnected = true;

        private bool _controllersDetected = false;

        private void Awake()
        {
            if (_instance != null && _instance != this)
            {
                Destroy(gameObject);
                return;
            }
            _instance = this;
            DontDestroyOnLoad(gameObject);
        }

        private void Start()
        {
            CheckControllers();
        }

        private void Update()
        {
            if (hideWhenControllerConnected && Time.frameCount % 60 == 0)
            {
                CheckControllers();
            }
        }

        private void CheckControllers()
        {
            string[] joysticks = Input.GetJoystickNames();
            bool hasGamepad = false;
            foreach (string joy in joysticks)
            {
                if (!string.IsNullOrEmpty(joy))
                {
                    hasGamepad = true;
                    break;
                }
            }

            if (hasGamepad != _controllersDetected)
            {
                _controllersDetected = hasGamepad;
                if (overlayCanvas != null)
                {
                    overlayCanvas.gameObject.SetActive(!_controllersDetected);
                }
            }
        }
    }
}
