using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace UAPorter.Editor
{
    /// <summary>
    /// Headless Android APK Builder executed via Unity batchmode.
    /// </summary>
    public static class PortBuilder
    {
        public static void BuildAndroid()
        {
            string[] args = Environment.GetCommandLineArgs();
            string outputPath = "build/out.apk";

            for (int i = 0; i < args.Length - 1; i++)
            {
                if (args[i] == "-apkOutput")
                {
                    outputPath = args[i + 1];
                    break;
                }
            }

            Directory.CreateDirectory(Path.GetDirectoryName(outputPath) ?? "build");

            UnityEngine.Debug.Log($"[UAPorter] Starting Headless Android Build -> {outputPath}");

            // Configure PlayerSettings for Android
            EditorUserBuildSettings.buildAppBundle = false;
            EditorUserBuildSettings.androidBuildSubtarget = MobileTextureSubtarget.Generic;
            EditorUserBuildSettings.androidBuildSystem = AndroidBuildSystem.Gradle;

            PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
            PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel24; // Android 7.0+
            
            // Gather all active scenes
            EditorBuildSettingsScene[] scenes = EditorBuildSettings.scenes;
            string[] scenePaths = new string[scenes.Length];
            for (int i = 0; i < scenes.Length; i++)
            {
                scenePaths[i] = scenes[i].path;
            }

            BuildPlayerOptions buildOptions = new BuildPlayerOptions
            {
                scenes = scenePaths,
                locationPathName = outputPath,
                target = BuildTarget.Android,
                options = BuildOptions.None
            };

            BuildReport report = BuildPipeline.BuildPlayer(buildOptions);
            BuildSummary summary = report.summary;

            if (summary.result == BuildResult.Succeeded)
            {
                UnityEngine.Debug.Log($"[UAPorter] Android Build Succeeded: {summary.totalSize} bytes");
                EditorApplication.Exit(0);
            }
            else
            {
                UnityEngine.Debug.LogError($"[UAPorter] Android Build Failed with {summary.totalErrors} errors!");
                EditorApplication.Exit(1);
            }
        }

        public static void BuildLinux()
        {
            string[] args = Environment.GetCommandLineArgs();
            string outputPath = "build/out.x86_64";

            for (int i = 0; i < args.Length - 1; i++)
            {
                if (args[i] == "-linuxOutput" || args[i] == "-customBuildPath")
                {
                    outputPath = args[i + 1];
                    break;
                }
            }

            Directory.CreateDirectory(Path.GetDirectoryName(outputPath) ?? "build");

            UnityEngine.Debug.Log($"[UAPorter] Starting Headless Linux Standalone Build -> {outputPath}");

            // Gather all active scenes
            EditorBuildSettingsScene[] scenes = EditorBuildSettings.scenes;
            string[] scenePaths = new string[scenes.Length];
            for (int i = 0; i < scenes.Length; i++)
            {
                scenePaths[i] = scenes[i].path;
            }

            BuildPlayerOptions buildOptions = new BuildPlayerOptions
            {
                scenes = scenePaths,
                locationPathName = outputPath,
                target = BuildTarget.StandaloneLinux64,
                options = BuildOptions.None
            };

            BuildReport report = BuildPipeline.BuildPlayer(buildOptions);
            BuildSummary summary = report.summary;

            if (summary.result == BuildResult.Succeeded)
            {
                UnityEngine.Debug.Log($"[UAPorter] Linux Build Succeeded: {summary.totalSize} bytes");
                EditorApplication.Exit(0);
            }
            else
            {
                UnityEngine.Debug.LogError($"[UAPorter] Linux Build Failed with {summary.totalErrors} errors!");
                EditorApplication.Exit(1);
            }
        }
    }
}
